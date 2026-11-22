import asyncio
import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app import db
from app.corpus_sync import CorpusSyncState, Page, parse_date_code, run_corpus_job
from app.embeddings import EmbeddingModels
from app.ingest import delete_document_chunks
from app.vector_store import VectorStore

logger = logging.getLogger(__name__)

ACTS_PATH = Path(__file__).parent / "data" / "law_acts.json"
LAW_PREFIX = "law:"
DZIENNIK_USTAW_URL = "https://dziennikustaw.gov.pl/DU/{year}/{position}"
LAW_LICENSE = "Akt normatywny, materiał urzędowy niechroniony prawem autorskim (art. 4 pkt 1 ustawy o prawie autorskim)"
# Footnote markers the scraper leaves at the end of titles ("Kodeks pracy1)").
TRAILING_FOOTNOTE = re.compile(r"(\s*\d+\))+$")
# PDF line wraps inside one article: a hyphen before a lowercase letter is a broken word, a newline not followed by
# an enumerator or a structural heading continues the sentence.
HYPHENATED_LINE_BREAK = re.compile(r"-\n(?=[a-ząćęłńóśźż])")
CONTINUATION_LINE_BREAK = re.compile(r"\n(?!(?:\d+\)|[a-z]\)|Art\.|§|Rozdział|DZIAŁ|Oddział|TYTUŁ|KSIĘGA|CZĘŚĆ))")
PARAGRAPH_SEPARATOR = "\n\n"

law_state = CorpusSyncState()
_law_lock = asyncio.Lock()


@dataclass(frozen=True)
class ActSpec:
    id: str
    label: str
    title_pattern: re.Pattern[str]


@dataclass(frozen=True)
class ActVersion:
    position: int
    year: int
    date: datetime
    title: str


def load_act_specs() -> list[ActSpec]:
    payload = json.loads(ACTS_PATH.read_text(encoding="utf-8"))
    return [
        ActSpec(id=item["id"], label=item["label"], title_pattern=re.compile(item["titlePattern"], re.IGNORECASE))
        for item in payload["acts"]
    ]


def normalize_title(title: str) -> str:
    return TRAILING_FOOTNOTE.sub("", " ".join(title.split()))


def newest_version(spec: ActSpec, candidates: list[ActVersion]) -> ActVersion | None:
    """The most recently announced act whose title matches the spec; a consolidated text replaces older ones."""
    matching = [act for act in candidates if spec.title_pattern.search(normalize_title(act.title))]
    if not matching:
        return None
    return max(matching, key=lambda act: (act.date, act.position))


def act_url(version: ActVersion) -> str:
    return DZIENNIK_USTAW_URL.format(year=version.year, position=version.position)


def join_wrapped_lines(rule: str) -> str:
    """One article as the scraper stored it, with PDF line wraps joined back into sentences."""
    return CONTINUATION_LINE_BREAK.sub(" ", HYPHENATED_LINE_BREAK.sub("", rule.strip()))


def act_text(version: ActVersion, rules: list[str]) -> str:
    paragraphs = [normalize_title(version.title)] + [join_wrapped_lines(rule) for rule in rules if rule.strip()]
    return PARAGRAPH_SEPARATOR.join(paragraphs)


def split_text(text: str, max_chars: int) -> list[str]:
    """Splits on paragraph boundaries so every part stays under the ingest limit; a single long paragraph is kept."""
    parts: list[str] = []
    current: list[str] = []
    current_length = 0
    for paragraph in text.split(PARAGRAPH_SEPARATOR):
        if current and current_length + len(paragraph) + len(PARAGRAPH_SEPARATOR) > max_chars:
            parts.append(PARAGRAPH_SEPARATOR.join(current))
            current, current_length = [], 0
        current.append(paragraph)
        current_length += len(paragraph) + len(PARAGRAPH_SEPARATOR)
    if current:
        parts.append(PARAGRAPH_SEPARATOR.join(current))
    return parts


def act_document_id(spec: ActSpec, part: int) -> str:
    return f"{LAW_PREFIX}{spec.id}" if part == 1 else f"{LAW_PREFIX}{spec.id}:{part}"


def act_pages(spec: ActSpec, version: ActVersion, rules: list[str], now: datetime, max_part_chars: int) -> list[Page]:
    parts = split_text(act_text(version, rules), max_part_chars)
    title = f"{spec.label} (Dz.U. {version.year} poz. {version.position})"
    return [
        Page(
            document_id=act_document_id(spec, index),
            url=act_url(version),
            title=title if len(parts) == 1 else f"{title}, część {index} z {len(parts)}",
            content=part,
            fetched_at=now,
            published_at=version.date,
            license=LAW_LICENSE,
        )
        for index, part in enumerate(parts, start=1)
    ]


def act_versions(rows: list) -> list[ActVersion]:
    """Rows of the Law table as versions; a row without a valid YYYYMMDD date is logged and left out, never guessed."""
    versions: list[ActVersion] = []
    for row in rows:
        date = parse_date_code(row["date"])
        if date is None:
            logger.warning("Law import: Dz.U. %s poz. %s has no valid date, skipped", row["year"], row["position"])
            continue
        versions.append(ActVersion(position=row["position"], year=row["year"], date=date, title=row["title"]))
    return versions


async def _already_indexed(pages: list[Page]) -> bool:
    """True only when every part of the act is active and comes from the same Dz.U. position."""
    for page in pages:
        if await db.active_document_url(page.document_id) != page.url:
            return False
    return True


async def _remove_stale_parts(spec: ActSpec, part_count: int, store: VectorStore) -> int:
    """A newer text split into fewer parts must not leave old parts behind as current law."""
    removed = 0
    part = part_count + 1
    while await db.active_document_url(act_document_id(spec, part)) is not None:
        removed += await delete_document_chunks(act_document_id(spec, part), store)
        part += 1
    return removed


async def import_law(
    models: EmbeddingModels, store: VectorStore, max_chars: int, max_part_chars: int
) -> CorpusSyncState:
    """
    Imports the newest version of every act in app/data/law_acts.json from the scraper's Law table, in list order,
    until `max_chars` of text have been queued. An act whose every part is already indexed from the same Dz.U.
    position is skipped, so a rerun continues where the budget stopped it.
    """
    planned: list[tuple[ActSpec, int]] = []

    async def load_pages(state: CorpusSyncState) -> list[Page]:
        candidates = act_versions(await db.fetch_law_acts())
        now = datetime.now(UTC)
        budget = max_chars
        pages: list[Page] = []
        for spec in load_act_specs():
            version = newest_version(spec, candidates)
            if version is None:
                state.failed += 1
                logger.warning("Law import: no act matches %s, skipped", spec.id)
                continue
            rules = await db.fetch_law_rules(version.position, version.year)
            act = act_pages(spec, version, rules, now, max_part_chars)
            if await _already_indexed(act):
                state.already_present += 1
                continue
            text_length = sum(len(page.content) for page in act)
            if text_length > budget:
                logger.info("Law import: budget used up before %s, rerun with higher maxChars", spec.id)
                break
            budget -= text_length
            pages.extend(act)
            planned.append((spec, len(act)))
        return pages

    state = await run_corpus_job(law_state, _law_lock, "Law import", load_pages, models, store, strip_boilerplate=False)
    for spec, part_count in planned:
        try:
            removed = await _remove_stale_parts(spec, part_count, store)
        except Exception:
            logger.exception("Law import: stale parts of %s could not be removed", spec.id)
            continue
        if removed:
            logger.info("Law import: %d stale chunks of %s removed", removed, spec.id)
    return state
