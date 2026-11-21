import asyncio
import hashlib
import json
import logging
import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx

from app import db
from app.catalog import SourceOutsideCatalogError, resolve_entry
from app.config import settings
from app.corpus_rules import exclusion_reason
from app.embeddings import EmbeddingModels
from app.fetcher import FetchError, fetch_page
from app.ingest import DuplicateDocumentError, delete_document_chunks, ingest_document
from app.models import DocumentIn, PruneReport, SourceIn
from app.vector_store import VectorStore

logger = logging.getLogger(__name__)

SCRAPED_PREFIX = "scrapped:"
WEB_PREFIX = "web:"
LAW_PREFIX = "law:"
BULK_IMPORT_PREFIXES = (SCRAPED_PREFIX, WEB_PREFIX, LAW_PREFIX)
WEB_ID_LENGTH = 16
YYYYMMDD = re.compile(r"^(\d{4})(\d{2})(\d{2})$")
TITLE_MAX_CHARS = 300
PROGRESS_EVERY = 20
SEED_URLS_PATH = Path(__file__).parent / "data" / "seed_urls.json"


@dataclass(frozen=True)
class Page:
    document_id: str
    url: str
    title: str
    content: str
    fetched_at: datetime
    published_at: datetime | None = None
    license: str | None = None


@dataclass
class CorpusSyncState:
    running: bool = False
    last_finished_at: datetime | None = None
    available: int | None = None
    indexed: int = 0
    already_present: int = 0
    skipped_duplicates: int = 0
    skipped_excluded: int = 0
    skipped_outside_catalog: int = 0
    failed: int = 0
    last_error: str | None = None

    def processed(self) -> int:
        skipped = self.skipped_duplicates + self.skipped_excluded + self.skipped_outside_catalog
        return self.indexed + skipped + self.failed

    def reset(self, running: bool) -> None:
        """Clears counters for a new run; progress fields keep their types for the status endpoints."""
        self.running = running
        self.last_finished_at = None
        self.available = None
        self.indexed = 0
        self.already_present = 0
        self.skipped_duplicates = 0
        self.skipped_excluded = 0
        self.skipped_outside_catalog = 0
        self.failed = 0
        self.last_error = None


sync_state = CorpusSyncState()
fetch_state = CorpusSyncState()
_sync_lock = asyncio.Lock()
_fetch_lock = asyncio.Lock()


def parse_date_code(value: int | None) -> datetime | None:
    """The scraper stores dates as YYYYMMDD integers; anything else is treated as unknown rather than guessed."""
    match = YYYYMMDD.match(str(value)) if value is not None else None
    if match is None:
        return None
    try:
        return datetime(int(match[1]), int(match[2]), int(match[3]), tzinfo=UTC)
    except ValueError:
        return None


def remove_boilerplate(contents: list[str], share: float, min_documents: int) -> list[str]:
    """
    Drops lines that repeat across a large share of pages (menus, cookie bars, footers), keeps everything else.
    Each remaining line becomes its own paragraph so chunking packs whole lines instead of cutting mid-sentence.
    """
    line_lists = [[line.strip() for line in content.splitlines() if line.strip()] for content in contents]
    document_frequency = Counter(line for lines in line_lists for line in set(lines))
    threshold = max(min_documents, int(len(contents) * share))
    boilerplate = (
        {line for line, count in document_frequency.items() if count >= threshold}
        if len(contents) >= min_documents
        else set()
    )
    return ["\n\n".join(line for line in lines if line not in boilerplate) for lines in line_lists]


def web_document_id(url: str) -> str:
    return WEB_PREFIX + hashlib.sha256(url.encode("utf-8")).hexdigest()[:WEB_ID_LENGTH]


def _seed_data() -> dict:
    return json.loads(SEED_URLS_PATH.read_text(encoding="utf-8"))


def seed_urls() -> list[str]:
    return _seed_data()["urls"]


def seed_published_at(url: str) -> datetime | None:
    """
    Publication date pinned for a seed page whose publisher exposes no machine-readable metadata.
    The date must be visible on the page itself (e.g. a legal act's Dz.U. date), never inferred.
    """
    raw = _seed_data().get("publishedAt", {}).get(url)
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        logger.warning("Seed publication date for %s is not ISO 8601, ignored", url)
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def to_document(page: Page, cleaned_content: str) -> DocumentIn:
    host = urlparse(page.url).hostname or page.url
    entry = resolve_entry(page.url)
    return DocumentIn(
        source=SourceIn(
            document_id=page.document_id,
            title=page.title.strip()[:TITLE_MAX_CHARS] or host,
            publisher=entry.publisher if entry else host,
            url=page.url,
            published_at=page.published_at,
            fetched_at=page.fetched_at,
            license=page.license,
            topic_tag=host,
        ),
        text=cleaned_content,
    )


async def _index_pages(
    pages: list[Page],
    models: EmbeddingModels,
    store: VectorStore,
    state: CorpusSyncState,
    label: str,
    strip_boilerplate: bool,
) -> None:
    """Normal ingest path for every page (catalog, duplicates, chunking); one bad page never stops the run."""
    cleaned = (
        remove_boilerplate(
            [page.content for page in pages],
            settings.corpus_boilerplate_share,
            settings.corpus_boilerplate_min_documents,
        )
        if strip_boilerplate
        else [page.content for page in pages]
    )
    for page, content in zip(pages, cleaned, strict=True):
        reason = exclusion_reason(page.url, page.title)
        if reason is not None:
            state.skipped_excluded += 1
            logger.info("%s: %s excluded by corpus rules (%s)", label, page.document_id, reason)
            continue
        if not content.strip():
            state.failed += 1
            continue
        try:
            await ingest_document(to_document(page, content), models, store)
            state.indexed += 1
        except DuplicateDocumentError as error:
            state.skipped_duplicates += 1
            logger.info("%s: %s duplicates %s, skipped", label, error.document_id, error.duplicate_of)
        except SourceOutsideCatalogError:
            state.skipped_outside_catalog += 1
            logger.warning("%s: %s is outside the source catalog, skipped", label, page.document_id)
        except Exception:
            state.failed += 1
            logger.exception("%s: %s failed", label, page.document_id)
        if state.processed() % PROGRESS_EVERY == 0:
            logger.info("%s: %d of %d pages processed, %d indexed", label, state.processed(), len(pages), state.indexed)


async def run_corpus_job(
    state: CorpusSyncState,
    lock: asyncio.Lock,
    label: str,
    load_pages,
    models: EmbeddingModels,
    store: VectorStore,
    strip_boilerplate: bool = True,
) -> CorpusSyncState:
    """
    One background import at a time per job: loads pages, indexes them, keeps the state for the status endpoint.
    `strip_boilerplate` drops lines shared by many pages (menus, footers); legal texts must stay verbatim, so law
    import turns it off.
    """
    if lock.locked():
        logger.warning("%s already running, request ignored", label)
        return state
    async with lock:
        state.reset(running=True)
        try:
            pages = await load_pages(state)
            state.available = len(pages)
            await _index_pages(pages, models, store, state, label, strip_boilerplate)
        except Exception as error:
            state.last_error = f"{type(error).__name__}: {error}"
            logger.exception("%s stopped", label)
        finally:
            state.running = False
            state.last_finished_at = datetime.now(UTC)
            logger.info(
                "%s done: %d indexed, %d already present, %d duplicates, %d excluded, %d outside catalog, %d failed",
                label,
                state.indexed,
                state.already_present,
                state.skipped_duplicates,
                state.skipped_excluded,
                state.skipped_outside_catalog,
                state.failed,
            )
    return state


async def prune_corpus(store: VectorStore, dry_run: bool = False) -> PruneReport:
    """
    Removes bulk-imported documents (scraper, fetched pages, law) that the corpus rules exclude; the same rules keep
    them out of every later import. Documents added by hand through POST /ingest are never touched.
    """
    document_ids: list[str] = []
    chunks_deleted = 0
    for row in await db.list_sources():
        if not row["document_id"].startswith(BULK_IMPORT_PREFIXES):
            continue
        reason = exclusion_reason(row["url"], row["title"])
        if reason is None:
            continue
        document_ids.append(row["document_id"])
        if dry_run:
            logger.info("Corpus prune (dry run): %s would be removed (%s)", row["document_id"], reason)
            continue
        chunks = await delete_document_chunks(row["document_id"], store)
        chunks_deleted += chunks
        logger.info("Corpus prune: %s removed, %d chunks (%s)", row["document_id"], chunks, reason)
    return PruneReport(
        dry_run=dry_run, documents_deleted=len(document_ids), chunks_deleted=chunks_deleted, document_ids=document_ids
    )


async def sync_corpus(models: EmbeddingModels, store: VectorStore, max_documents: int) -> CorpusSyncState:
    """Imports the scraper's pages from the shared database table into the evidence corpus."""

    async def load_pages(_: CorpusSyncState) -> list[Page]:
        rows = await db.fetch_scraped_pages(max_documents)
        return [
            Page(
                document_id=f"{SCRAPED_PREFIX}{row['id']}",
                url=row["site"],
                title=row["title"] or "",
                content=row["content"] or "",
                fetched_at=parse_date_code(row["date"]) or datetime.now(UTC),
            )
            for row in rows
        ]

    return await run_corpus_job(sync_state, _sync_lock, "Corpus sync", load_pages, models, store)


async def fetch_corpus(
    urls: list[str], models: EmbeddingModels, store: VectorStore, transport: httpx.AsyncBaseTransport | None = None
) -> CorpusSyncState:
    """
    Fetches public pages (seed list or caller's URLs) and indexes them like scraped ones. Pages that fail to
    download or are not HTML count as failed; the rest go through the catalog, so unknown domains are skipped.
    """

    async def load_pages(state: CorpusSyncState) -> list[Page]:
        pages: list[Page] = []
        async with httpx.AsyncClient(
            timeout=settings.corpus_fetch_timeout_seconds, follow_redirects=True, transport=transport
        ) as client:
            for url in urls:
                try:
                    fetched = await fetch_page(client, url)
                except FetchError as error:
                    state.failed += 1
                    logger.warning("Corpus fetch: %s skipped (%s)", url, error)
                    continue
                pages.append(
                    Page(
                        document_id=web_document_id(url),
                        url=fetched.url,
                        title=fetched.title,
                        content=fetched.text,
                        fetched_at=datetime.now(UTC),
                        published_at=fetched.published_at or seed_published_at(url),
                    )
                )
                await asyncio.sleep(settings.corpus_fetch_delay_seconds)
        return pages

    return await run_corpus_job(fetch_state, _fetch_lock, "Corpus fetch", load_pages, models, store)
