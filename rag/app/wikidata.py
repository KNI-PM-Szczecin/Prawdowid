import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from uuid import NAMESPACE_URL, UUID, uuid5

import httpx

from app.caching import TtlCache
from app.config import settings
from app.models import ExternalSourceStatus

logger = logging.getLogger(__name__)

SOURCE_NAME = "wikidata"
PUBLISHER = "Wikidata (Wikimedia Foundation)"
LICENSE = "CC0 1.0 (dane strukturalne Wikidata)"
ENTITY_URL = "https://www.wikidata.org/wiki/{entity_id}"
HUMAN = "Q5"
INSTANCE_OF, BIRTH, DEATH = "P31", "P569", "P570"
# A capitalised name of up to three words, optionally after a title ("Królowa Elżbieta", "papież Franciszek").
TITLES = r"(?:[Kk]r[oó]low[aą]|[Kk]r[oó]l|[Pp]apie[zż]|[Kk]si[aą][zż][eę]|[Pp]rezydent|[Pp]remier|[Mm]arsza[lł]ek)"
NAME_WORD = r"[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+(?:-[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+)?"
PERSON_MENTION = re.compile(rf"(?:{TITLES}\s+)?{NAME_WORD}(?:\s+{NAME_WORD}){{0,2}}")
MONTHS = (
    "stycznia",
    "lutego",
    "marca",
    "kwietnia",
    "maja",
    "czerwca",
    "lipca",
    "sierpnia",
    "września",
    "października",
    "listopada",
    "grudnia",
)
# Wikidata time precision 11 is a day; coarser values (year, month) are shown as the year only.
DAY_PRECISION = 11


@dataclass(frozen=True)
class PersonFact:
    entity_id: str
    label: str
    description: str | None
    born: str | None
    died: str | None
    modified: datetime | None

    @property
    def fact_id(self) -> UUID:
        return uuid5(NAMESPACE_URL, self.url)

    @property
    def url(self) -> str:
        return ENTITY_URL.format(entity_id=self.entity_id)

    @property
    def passage_text(self) -> str:
        """Polish summary shown as the passage; every fact comes from Wikidata's structured data."""
        description = f" ({self.description})" if self.description else ""
        # Formatted dates end with "r.", which already closes the sentence.
        born = f" Data urodzenia: {self.born}" if self.born else ""
        died = f" Data śmierci: {self.died}" if self.died else " W danych nie ma daty śmierci."
        return f"{self.label}{description}.{born}{died}"

    @property
    def rerank_text(self) -> str:
        return self.passage_text


@dataclass(frozen=True)
class WikidataResult:
    status: str
    facts: list[PersonFact]

    def as_status(self) -> ExternalSourceStatus:
        return ExternalSourceStatus(name=SOURCE_NAME, status=self.status, results=len(self.facts))


def person_mentions(text: str) -> list[str]:
    """Capitalised names in the claim, longest first per position, without duplicates."""
    mentions = dict.fromkeys(match.group(0) for match in PERSON_MENTION.finditer(text))
    return list(mentions)[: settings.wikidata_max_people]


def format_time(value: dict) -> str | None:
    """'+2022-09-08T00:00:00Z' with day precision -> '8 września 2022 r.'; coarser precision -> the year."""
    time = str(value.get("time") or "")
    match = re.match(r"^[+-](\d{1,4})-(\d{2})-(\d{2})", time)
    if not match:
        return None
    year, month, day = (int(part) for part in match.groups())
    if int(value.get("precision") or 0) >= DAY_PRECISION and month and day:
        return f"{day} {MONTHS[month - 1]} {year} r."
    return f"{year} r."


def _claim_value(claims: dict, prop: str) -> dict | None:
    for statement in claims.get(prop, []):
        value = statement.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(value, dict):
            return value
    return None


def _is_human(claims: dict) -> bool:
    return any(
        statement.get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id") == HUMAN
        for statement in claims.get(INSTANCE_OF, [])
    )


def _parse_modified(raw: object) -> datetime | None:
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_people(entities: dict) -> list[PersonFact]:
    """Humans only; an entity without a Polish label cannot be shown, so it is skipped."""
    facts: list[PersonFact] = []
    for entity_id, entity in entities.items():
        claims = entity.get("claims", {})
        label = entity.get("labels", {}).get("pl", {}).get("value")
        if not label or not _is_human(claims):
            continue
        born, died = _claim_value(claims, BIRTH), _claim_value(claims, DEATH)
        facts.append(
            PersonFact(
                entity_id=entity_id,
                label=label,
                description=entity.get("descriptions", {}).get("pl", {}).get("value"),
                born=format_time(born) if born else None,
                died=format_time(died) if died else None,
                modified=_parse_modified(entity.get("modified")),
            )
        )
    return facts


class WikidataClient:
    """Live Wikidata lookup of people named in a claim; never raises, failures become an explicit `error` status."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._client = httpx.AsyncClient(
            timeout=settings.wikidata_timeout_seconds,
            transport=transport,
            headers={"User-Agent": settings.hop_user_agent},
        )
        self._cache: TtlCache[str, list[PersonFact]] = TtlCache(
            settings.wikidata_cache_ttl_seconds, settings.wikidata_cache_max_entries
        )

    @property
    def enabled(self) -> bool:
        return settings.wikidata_enabled

    async def people(self, claim: str) -> WikidataResult:
        """Facts about the first wikidata_max_people names in the claim that Wikidata knows as humans."""
        if not self.enabled:
            return WikidataResult(status="disabled", facts=[])
        mentions = person_mentions(claim)
        if not mentions:
            return WikidataResult(status="skipped", facts=[])
        outcomes = await asyncio.gather(*(self._lookup(mention) for mention in mentions))
        if all(outcome is None for outcome in outcomes):
            return WikidataResult(status="error", facts=[])
        merged: dict[str, PersonFact] = {}
        for facts in outcomes:
            for fact in facts or []:
                merged.setdefault(fact.entity_id, fact)
        return WikidataResult(status="ok", facts=list(merged.values())[: settings.wikidata_max_people])

    async def _lookup(self, mention: str) -> list[PersonFact] | None:
        cached = self._cache.get(mention)
        if cached is not None:
            return cached
        try:
            found = await self._get(
                {
                    "action": "wbsearchentities",
                    "search": mention,
                    "language": "pl",
                    "uselang": "pl",
                    "type": "item",
                    "limit": settings.wikidata_search_limit,
                    "format": "json",
                }
            )
            ids = [item["id"] for item in found.get("search", []) if isinstance(item, dict) and item.get("id")]
            facts: list[PersonFact] = []
            if ids:
                entities = await self._get(
                    {
                        "action": "wbgetentities",
                        "ids": "|".join(ids),
                        "props": "claims|labels|descriptions|info",
                        "languages": "pl",
                        "format": "json",
                    }
                )
                # The first human in search order is the person meant; later ones are namesakes.
                by_id = entities.get("entities", {})
                facts = parse_people({entity_id: by_id[entity_id] for entity_id in ids if entity_id in by_id})[:1]
        except (httpx.HTTPError, ValueError, KeyError) as error:
            logger.warning("Wikidata lookup failed: %s", type(error).__name__)
            return None
        self._cache.put(mention, facts)
        return facts

    async def _get(self, params: dict) -> dict:
        response = await self._client.get(settings.wikidata_api_url, params=params)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Wikidata answer is not a JSON object")
        return payload

    async def close(self) -> None:
        await self._client.aclose()
