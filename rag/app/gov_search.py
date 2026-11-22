import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import unquote, urljoin, urlparse

import httpx

from app import db
from app.caching import TtlCache
from app.catalog import resolve_entry
from app.config import settings
from app.corpus_rules import exclusion_reason
from app.corpus_sync import Page, remove_boilerplate, to_document, web_document_id
from app.countries import country_mentions, fold
from app.embeddings import EmbeddingModels
from app.fetcher import FetchError, fetch_page
from app.ingest import DuplicateDocumentError, delete_document_chunks, ingest_document
from app.lexical import WORD, content_words
from app.models import ExternalSourceStatus, Passage, SearchRequest
from app.vector_store import VectorStore

logger = logging.getLogger(__name__)

SOURCE_NAME = "gov_search"
OFFICIAL_SOURCE_TYPE = "official"
# Fetched pages share gov.pl navigation; a line on two of them is a menu, not content.
BOILERPLATE_MIN_PAGES = 2
# Polish inflects ("strajk", "strajku", "strajkiem"), so topic words are compared by their first letters.
TOPIC_KEY_CHARS = 5
TOPIC_WORD_MIN_CHARS = 3


@dataclass(frozen=True)
class GovSearchHit:
    title: str
    url: str
    published_at: datetime


@dataclass
class GapFillResult:
    status: str
    indexed: int = 0

    def as_status(self) -> ExternalSourceStatus:
        return ExternalSourceStatus(name=SOURCE_NAME, status=self.status, results=self.indexed)


def parse_hits(payload: dict) -> list[GovSearchHit]:
    """Hits in gov.pl relevance order; a hit without a publication date is dropped, it could never be evidence."""
    hits: list[GovSearchHit] = []
    for item in payload.get("results") or []:
        raw_date, path = item.get("publishDate"), item.get("url")
        if not raw_date or not path:
            continue
        try:
            published = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
        except ValueError:
            continue
        hits.append(
            GovSearchHit(
                title=(item.get("title") or "").strip(),
                url=urljoin(settings.gov_search_site, path),
                published_at=published if published.tzinfo else published.replace(tzinfo=UTC),
            )
        )
    return hits


def _topic_keys(words: list[str]) -> set[str]:
    return {fold(word)[:TOPIC_KEY_CHARS] for word in words if len(word) >= TOPIC_WORD_MIN_CHARS and not word.isdigit()}


def _named_words(claim: str) -> list[str]:
    """
    Capitalised words inside a sentence (a city, a region, an institution); the first word of a sentence is
    capitalised anyway and acronyms (ZUS, NATO) rarely appear in gov.pl titles, so neither is required.
    """
    named: list[str] = []
    sentence_start = True
    for word in WORD.findall(claim):
        if not sentence_start and word[:1].isupper() and not word.isupper():
            named.append(word)
        sentence_start = False
    return named


def _hit_text(hit: GovSearchHit) -> str:
    return f"{hit.title} {unquote(urlparse(hit.url).path)}"


def relevant_hits(hits: list[GovSearchHit], claim: str) -> list[GovSearchHit]:
    """
    Drops gov.pl hits that cannot be about the claim, before anything is downloaded: excluded pages (schools, job
    offers), hits whose title and address share no topic word with the claim, and, when the claim names a country or
    another place, hits that do not name it (a strike in Belgium is no evidence about a strike in another country).
    """
    mentions = country_mentions(claim)
    countries = {mention.country for mention in mentions}
    country_words = {word for mention in mentions for word in mention.nominatives}
    named_keys = _topic_keys([word for word in _named_words(claim) if fold(word) not in country_words])
    topic_keys = _topic_keys([word for word in content_words(claim) if fold(word) not in country_words]) - named_keys
    relevant: list[GovSearchHit] = []
    for hit in hits:
        if exclusion_reason(hit.url, hit.title) is not None:
            continue
        text = _hit_text(hit)
        hit_keys = _topic_keys(content_words(text))
        if topic_keys and not topic_keys & hit_keys:
            continue
        if countries and not countries & {mention.country for mention in country_mentions(text.lower())}:
            continue
        if not countries and named_keys and not named_keys & hit_keys:
            continue
        relevant.append(hit)
    return relevant


def select_hits(hits: list[GovSearchHit], max_pages: int) -> list[GovSearchHit]:
    """
    Relevance and currency together: the best gov.pl match is always taken (it may describe the earlier state),
    the remaining slots go to the newest of the other relevant hits, so the current state is in the corpus too.
    """
    if not hits:
        return []
    best, others = hits[0], hits[1:]
    newest = sorted(others, key=lambda hit: hit.published_at, reverse=True)
    return [best, *newest][:max_pages]


def wanted(request: SearchRequest, found: list[Passage]) -> bool:
    """Fill the gap when the corpus has too few passages or none of them is a clearly relevant match."""
    filters = request.filters
    if filters is not None and filters.source_types and OFFICIAL_SOURCE_TYPE not in filters.source_types:
        return False
    if len(found) < settings.gov_search_min_results:
        return True
    return max(passage.score for passage in found) < settings.gov_search_sufficient_score


class GovSearchClient:
    """
    Fills corpus gaps from gov.pl: the search endpoint behind gov.pl/web/gov/szukaj (robots.txt allows all) finds
    pages for a claim the corpus cannot answer, and the chosen pages go through the normal ingest path (catalog,
    exclusion rules, duplicates). Only the claim text leaves the system, to a Polish government service.
    """

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._client = httpx.AsyncClient(
            timeout=settings.gov_search_timeout_seconds, follow_redirects=False, transport=transport
        )
        self._cache: TtlCache[str, list[GovSearchHit]] = TtlCache(
            settings.gov_search_cache_ttl_seconds, settings.gov_search_cache_max_entries
        )
        self._lock = asyncio.Lock()
        self._background: set[asyncio.Task] = set()

    @property
    def enabled(self) -> bool:
        return settings.gov_search_enabled

    async def search(self, query: str) -> list[GovSearchHit]:
        cached = self._cache.get(query)
        if cached is not None:
            return cached
        response = await self._client.get(
            settings.gov_search_url,
            params={"query": query, "page": 1, "size": settings.gov_search_candidates},
            headers={"User-Agent": settings.corpus_fetch_user_agent, "Accept": "application/json"},
        )
        response.raise_for_status()
        hits = parse_hits(response.json())
        self._cache.put(query, hits)
        return hits

    async def _stored_recently(self, document_id: str, now: datetime) -> bool:
        fetched_at = await db.document_fetched_at(document_id)
        return fetched_at is not None and now - fetched_at < timedelta(days=settings.gov_search_refresh_days)

    async def _fetch(self, hits: list[GovSearchHit], now: datetime) -> list[tuple[Page, bool]]:
        """Downloads the chosen pages; a copy fetched within the refresh window is kept and not downloaded again."""
        pages: list[tuple[Page, bool]] = []
        for hit in hits:
            document_id = web_document_id(hit.url)
            if await self._stored_recently(document_id, now):
                continue
            try:
                fetched = await fetch_page(self._client, hit.url)
            except FetchError as error:
                logger.warning("gov.pl gap fill: %s skipped (%s)", hit.url, error)
                continue
            stale_copy = bool(await db.active_chunk_ids_for_document(document_id))
            pages.append(
                (
                    Page(
                        document_id=document_id,
                        url=hit.url,
                        title=fetched.title or hit.title,
                        content=fetched.text,
                        fetched_at=now,
                        # gov.pl's own publication date beats page metadata: it is what the portal shows readers.
                        published_at=hit.published_at,
                    ),
                    stale_copy,
                )
            )
        return pages

    async def _index(self, pages: list[tuple[Page, bool]], models: EmbeddingModels, store: VectorStore) -> int:
        contents = [page.content for page, _ in pages]
        cleaned = (
            remove_boilerplate(contents, settings.corpus_boilerplate_share, BOILERPLATE_MIN_PAGES)
            if len(pages) >= BOILERPLATE_MIN_PAGES
            else contents
        )
        indexed = 0
        for (page, stale_copy), content in zip(pages, cleaned, strict=True):
            if resolve_entry(page.url) is None or exclusion_reason(page.url, page.title) is not None:
                logger.info("gov.pl gap fill: %s outside the catalog or excluded", page.url)
                continue
            if not content.strip():
                continue
            if stale_copy:
                # Replaced only after the new copy downloaded, so a failed refresh never loses the old evidence.
                await delete_document_chunks(page.document_id, store)
            try:
                await ingest_document(to_document(page, content), models, store)
                indexed += 1
            except DuplicateDocumentError as error:
                logger.info("gov.pl gap fill: %s duplicates %s", error.document_id, error.duplicate_of)
            except Exception:
                logger.exception("gov.pl gap fill: %s failed", page.document_id)
        return indexed

    async def _fill(self, query: str, claim: str, models: EmbeddingModels, store: VectorStore) -> int:
        found = await self.search(query)
        hits = select_hits(relevant_hits(found, claim), settings.gov_search_max_pages)
        if not hits:
            logger.info("gov.pl gap fill: none of %d hits is about the claim", len(found))
            return 0
        async with self._lock:
            pages = await self._fetch(hits, datetime.now(UTC))
            indexed = await self._index(pages, models, store) if pages else 0
        logger.info("gov.pl gap fill: %d of %d chosen pages indexed", indexed, len(hits))
        return indexed

    async def fill(
        self, query: str, models: EmbeddingModels, store: VectorStore, claim: str | None = None
    ) -> GapFillResult:
        """
        Runs inside the search request for at most gov_search_budget_seconds. A slower fill keeps running in the
        background, so the pages still reach the corpus for the next question; the current answer is not delayed.
        `query` goes to the gov.pl search (keywords); `claim` (default: the query) decides which hits are relevant.
        """
        if not self.enabled:
            return GapFillResult(status="disabled")
        task = asyncio.create_task(self._fill(query, claim or query, models, store))
        try:
            indexed = await asyncio.wait_for(asyncio.shield(task), settings.gov_search_budget_seconds)
        except TimeoutError:
            self._background.add(task)
            task.add_done_callback(self._finished_in_background)
            logger.info("gov.pl gap fill over budget, continues in the background")
            return GapFillResult(status="ok")
        except (httpx.HTTPError, ValueError) as error:
            logger.warning("gov.pl search failed: %s", type(error).__name__)
            return GapFillResult(status="error")
        return GapFillResult(status="ok", indexed=indexed)

    def _finished_in_background(self, task: asyncio.Task) -> None:
        self._background.discard(task)
        if task.cancelled():
            return
        if (error := task.exception()) is not None:
            logger.warning("gov.pl gap fill in the background failed: %s", type(error).__name__)

    async def close(self) -> None:
        for task in self._background:
            task.cancel()
        await self._client.aclose()
