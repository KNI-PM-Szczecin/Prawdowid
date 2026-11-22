import asyncio
import itertools
import logging
import re
from dataclasses import dataclass, replace
from datetime import datetime
from uuid import NAMESPACE_URL, UUID, uuid5

import httpx

from app.caching import TtlCache
from app.config import settings
from app.languages import load_profile
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
PARTY, POSITION = "P102", "P39"
START, END = "P580", "P582"
# Past offices shown per person, most recent first; current ones are always shown.
MAX_PAST_POSITIONS = 3
# Polish first, then the multilingual label that many people now have instead of a Polish one.
LABEL_LANGUAGES = "pl|mul"
# wbgetentities accepts at most 50 ids per request.
MAX_LABEL_IDS = 50
# A name written in lowercase ("jarosław kaczyński należy…") is looked up as the first pair of adjacent content words.
MIN_NAME_WORD_LENGTH = 3
LOWERCASE_WORD = re.compile(r"[a-ząćęłńóśźż]+")


@dataclass(frozen=True)
class Role:
    """A party membership or an office, with the years from its start and end qualifiers when Wikidata has them."""

    kind: str
    entity_id: str
    start: int | None
    end: int | None


@dataclass(frozen=True)
class PersonFact:
    entity_id: str
    label: str
    description: str | None
    born: str | None
    died: str | None
    modified: datetime | None
    roles: tuple[Role, ...] = ()
    role_lines: tuple[str, ...] = ()

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
        roles = "".join(f" {line}" for line in self.role_lines)
        return f"{self.label}{description}.{born}{died}{roles}"

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
    """
    Capitalised names in the claim, without duplicates. A claim written without any capital letter gets its first
    pair of adjacent content words as the candidate name ("jarosław kaczyński należy…" -> "Jarosław Kaczyński").
    """
    mentions = list(dict.fromkeys(match.group(0) for match in PERSON_MENTION.finditer(text)))
    if not mentions and not any(character.isupper() for character in text):
        stopwords = load_profile(settings.corpus_language).stopwords
        words = LOWERCASE_WORD.findall(text)
        for first, second in itertools.pairwise(words):
            if all(len(word) >= MIN_NAME_WORD_LENGTH and word not in stopwords for word in (first, second)):
                mentions.append(f"{first.capitalize()} {second.capitalize()}")
                break
    return mentions[: settings.wikidata_max_people]


def _year(value: dict | None) -> int | None:
    match = re.match(r"^[+-](\d{1,4})", str((value or {}).get("time") or ""))
    return int(match.group(1)) if match else None


def _qualifier_time(statement: dict, prop: str) -> dict | None:
    for qualifier in statement.get("qualifiers", {}).get(prop, []):
        value = qualifier.get("datavalue", {}).get("value")
        if isinstance(value, dict):
            return value
    return None


def _roles(claims: dict) -> tuple[Role, ...]:
    roles: list[Role] = []
    for kind in (PARTY, POSITION):
        for statement in claims.get(kind, []):
            value = statement.get("mainsnak", {}).get("datavalue", {}).get("value")
            if isinstance(value, dict) and value.get("id"):
                roles.append(
                    Role(
                        kind=kind,
                        entity_id=value["id"],
                        start=_year(_qualifier_time(statement, START)),
                        end=_year(_qualifier_time(statement, END)),
                    )
                )
    return tuple(roles)


def describe_roles(roles: tuple[Role, ...], labels: dict[str, str]) -> tuple[str, ...]:
    """
    Polish sentences about parties and offices. A role without an end date in Wikidata is shown as current, the rest
    with their years; roles whose label is unknown are skipped rather than shown as a bare identifier.
    """

    def named(kind: str, current: bool) -> list[Role]:
        chosen = [
            role for role in roles if role.kind == kind and (role.end is None) == current and role.entity_id in labels
        ]
        return sorted(chosen, key=lambda role: role.end or role.start or 0, reverse=True)

    def since(role: Role) -> str:
        return f"{labels[role.entity_id]} (od {role.start} r.)" if role.start else labels[role.entity_id]

    def span(role: Role) -> str:
        years = f"{role.start}-{role.end}" if role.start else f"do {role.end}"
        return f"{labels[role.entity_id]} ({years} r.)"

    lines: list[str] = []
    if parties := list(dict.fromkeys(since(role) for role in named(PARTY, current=True))):
        lines.append(f"Przynależność partyjna (według Wikidaty, bez daty zakończenia): {', '.join(parties)}.")
    if past_parties := list(dict.fromkeys(span(role) for role in named(PARTY, current=False))):
        lines.append(f"Wcześniejsza przynależność partyjna: {', '.join(past_parties)}.")
    if offices := list(dict.fromkeys(since(role) for role in named(POSITION, current=True))):
        lines.append(f"Pełnione funkcje (bez daty zakończenia w Wikidacie): {', '.join(offices)}.")
    if past_offices := list(dict.fromkeys(span(role) for role in named(POSITION, current=False)))[:MAX_PAST_POSITIONS]:
        lines.append(f"Wcześniejsze funkcje: {', '.join(past_offices)}.")
    return tuple(lines)


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


def polish_label(entity: dict) -> str | None:
    """The Polish label, else the multilingual one ("mul"), which Wikidata now keeps for names shared by languages."""
    labels = entity.get("labels", {})
    for language in LABEL_LANGUAGES.split("|"):
        if value := labels.get(language, {}).get("value"):
            return value
    return None


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
        label = polish_label(entity)
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
                roles=_roles(claims),
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
                        "languages": LABEL_LANGUAGES,
                        "format": "json",
                    }
                )
                # The first human in search order is the person meant; later ones are namesakes.
                by_id = entities.get("entities", {})
                facts = parse_people({entity_id: by_id[entity_id] for entity_id in ids if entity_id in by_id})[:1]
                facts = [await self._with_roles(fact) for fact in facts]
        except (httpx.HTTPError, ValueError, KeyError) as error:
            logger.warning("Wikidata lookup failed: %s", type(error).__name__)
            return None
        self._cache.put(mention, facts)
        return facts

    async def _with_roles(self, fact: PersonFact) -> PersonFact:
        """Adds the parties and offices in Polish; one request for the labels of all of them."""
        role_ids = list(dict.fromkeys(role.entity_id for role in fact.roles))[:MAX_LABEL_IDS]
        if not role_ids:
            return fact
        answer = await self._get(
            {
                "action": "wbgetentities",
                "ids": "|".join(role_ids),
                "props": "labels",
                "languages": LABEL_LANGUAGES,
                "format": "json",
            }
        )
        labels = {
            entity_id: label
            for entity_id, entity in answer.get("entities", {}).items()
            if (label := polish_label(entity))
        }
        return replace(fact, role_lines=describe_roles(fact.roles, labels))

    async def _get(self, params: dict) -> dict:
        response = await self._client.get(settings.wikidata_api_url, params=params)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Wikidata answer is not a JSON object")
        return payload

    async def close(self) -> None:
        await self._client.aclose()
