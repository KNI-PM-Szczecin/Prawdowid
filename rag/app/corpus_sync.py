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
from app.embeddings import EmbeddingModels
from app.fetcher import FetchError, fetch_page
from app.ingest import DuplicateDocumentError, ingest_document
from app.models import DocumentIn, SourceIn
from app.vector_store import VectorStore

logger = logging.getLogger(__name__)

SCRAPED_PREFIX = "scrapped:"
WEB_PREFIX = "web:"
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


@dataclass
class CorpusSyncState:
    running: bool = False
    last_finished_at: datetime | None = None
    available: int | None = None
    indexed: int = 0
    skipped_duplicates: int = 0
    skipped_outside_catalog: int = 0
    failed: int = 0
    last_error: str | None = None


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


def seed_urls() -> list[str]:
    return json.loads(SEED_URLS_PATH.read_text(encoding="utf-8"))["urls"]


def to_document(page: Page, cleaned_content: str) -> DocumentIn:
    host = urlparse(page.url).hostname or page.url
    entry = resolve_entry(page.url)
    return DocumentIn(
        source=SourceIn(
            document_id=page.document_id,
            title=page.title.strip()[:TITLE_MAX_CHARS] or host,
            publisher=entry.publisher if entry else host,
            url=page.url,
            published_at=None,
            fetched_at=page.fetched_at,
            license=None,
            topic_tag=host,
        ),
        text=cleaned_content,
    )


async def _index_pages(
    pages: list[Page], models: EmbeddingModels, store: VectorStore, state: CorpusSyncState, label: str
) -> None:
    """Normal ingest path for every page (catalog, duplicates, chunking); one bad page never stops the run."""
    cleaned = remove_boilerplate(
        [page.content for page in pages], settings.corpus_boilerplate_share, settings.corpus_boilerplate_min_documents
    )
    for page, content in zip(pages, cleaned, strict=True):
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
        done = state.indexed + state.skipped_duplicates + state.skipped_outside_catalog + state.failed
        if done % PROGRESS_EVERY == 0:
            logger.info("%s: %d of %d pages processed, %d indexed", label, done, len(pages), state.indexed)


async def _run(
    state: CorpusSyncState, lock: asyncio.Lock, label: str, load_pages, models: EmbeddingModels, store: VectorStore
) -> CorpusSyncState:
    if lock.locked():
        logger.warning("%s already running, request ignored", label)
        return state
    async with lock:
        state.__init__(running=True)
        try:
            pages = await load_pages(state)
            state.available = len(pages)
            await _index_pages(pages, models, store, state, label)
        except Exception as error:
            state.last_error = f"{type(error).__name__}: {error}"
            logger.exception("%s stopped", label)
        finally:
            state.running = False
            state.last_finished_at = datetime.now(UTC)
            logger.info(
                "%s done: %d indexed, %d duplicates, %d outside catalog, %d failed",
                label,
                state.indexed,
                state.skipped_duplicates,
                state.skipped_outside_catalog,
                state.failed,
            )
    return state


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

    return await _run(sync_state, _sync_lock, "Corpus sync", load_pages, models, store)


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
                    )
                )
                await asyncio.sleep(settings.corpus_fetch_delay_seconds)
        return pages

    return await _run(fetch_state, _fetch_lock, "Corpus fetch", load_pages, models, store)
