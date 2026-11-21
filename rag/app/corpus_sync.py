import asyncio
import logging
import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlparse

from app import db
from app.catalog import SourceOutsideCatalogError, resolve_entry
from app.config import settings
from app.embeddings import EmbeddingModels
from app.ingest import DuplicateDocumentError, ingest_document
from app.models import DocumentIn, SourceIn
from app.vector_store import VectorStore

logger = logging.getLogger(__name__)

DOCUMENT_PREFIX = "scrapped:"
YYYYMMDD = re.compile(r"^(\d{4})(\d{2})(\d{2})$")
TITLE_MAX_CHARS = 300


@dataclass(frozen=True)
class ScrapedPage:
    row_id: int
    date_code: int | None
    site: str
    title: str
    content: str


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
_sync_lock = asyncio.Lock()


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


def to_document(page: ScrapedPage, cleaned_content: str) -> DocumentIn:
    host = urlparse(page.site).hostname or page.site
    entry = resolve_entry(page.site)
    fetched_at = parse_date_code(page.date_code) or datetime.now(UTC)
    return DocumentIn(
        source=SourceIn(
            document_id=f"{DOCUMENT_PREFIX}{page.row_id}",
            title=page.title.strip()[:TITLE_MAX_CHARS] or host,
            publisher=entry.publisher if entry else host,
            url=page.site,
            published_at=None,
            fetched_at=fetched_at,
            license=None,
            topic_tag=host,
        ),
        text=cleaned_content,
    )


async def sync_corpus(models: EmbeddingModels, store: VectorStore, max_documents: int) -> CorpusSyncState:
    """
    Imports the scraper's pages from the shared database into the evidence corpus through the normal ingest path
    (catalog qualification, duplicate rejection, chunking). One bad page never stops the run; counts say what happened.
    """
    if _sync_lock.locked():
        logger.warning("Corpus sync already running, request ignored")
        return sync_state
    async with _sync_lock:
        sync_state.running = True
        sync_state.last_error = None
        indexed = duplicates = outside = failed = 0
        try:
            rows = await db.fetch_scraped_pages(max_documents)
            pages = [
                ScrapedPage(row["id"], row["date"], row["site"], row["title"] or "", row["content"] or "")
                for row in rows
            ]
            sync_state.available = len(pages)
            cleaned = remove_boilerplate(
                [page.content for page in pages],
                settings.corpus_boilerplate_share,
                settings.corpus_boilerplate_min_documents,
            )
            for page, content in zip(pages, cleaned, strict=True):
                if not content.strip():
                    failed += 1
                    continue
                try:
                    await ingest_document(to_document(page, content), models, store)
                    indexed += 1
                except DuplicateDocumentError as error:
                    duplicates += 1
                    logger.info("Corpus sync: %s duplicates %s, skipped", error.document_id, error.duplicate_of)
                except SourceOutsideCatalogError:
                    outside += 1
                    logger.warning("Corpus sync: page %s is outside the source catalog, skipped", page.row_id)
                except Exception:
                    failed += 1
                    logger.exception("Corpus sync: page %s failed", page.row_id)
                if (indexed + duplicates + outside + failed) % 20 == 0:
                    logger.info(
                        "Corpus sync: %d indexed, %d duplicates, %d outside catalog, %d failed",
                        indexed,
                        duplicates,
                        outside,
                        failed,
                    )
        except Exception as error:
            sync_state.last_error = f"{type(error).__name__}: {error}"
            logger.exception("Corpus sync stopped")
        finally:
            sync_state.running = False
            sync_state.last_finished_at = datetime.now(UTC)
            sync_state.indexed, sync_state.skipped_duplicates = indexed, duplicates
            sync_state.skipped_outside_catalog, sync_state.failed = outside, failed
            logger.info(
                "Corpus sync done: %d indexed, %d duplicates, %d outside catalog, %d failed",
                indexed,
                duplicates,
                outside,
                failed,
            )
    return sync_state
