import asyncio
import hashlib
import json
import logging
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

import httpx

from app import db
from app.config import settings
from app.corpus_sync import CorpusSyncState, Page, run_corpus_job
from app.embeddings import EmbeddingModels
from app.fetcher import FetchedPage, FetchError, fetch_page
from app.vector_store import VectorStore

logger = logging.getLogger(__name__)

FEEDS_PATH = Path(__file__).parent / "data" / "feeds.json"
FEED_PREFIX = "feed:"
FEED_ID_LENGTH = 16
HTTP_URL_SCHEMES = ("http://", "https://")
# Police servers drop connections that arrive in bursts, so a page gets a few spaced attempts before it fails.
FETCH_ATTEMPTS = 3

feed_state = CorpusSyncState()
_feed_lock = asyncio.Lock()


@dataclass(frozen=True)
class Feed:
    name: str
    url: str
    max_items: int
    exempt_hosts: frozenset[str]


@dataclass(frozen=True)
class FeedItem:
    title: str
    link: str
    published_at: datetime | None


def load_feeds() -> list[Feed]:
    payload = json.loads(FEEDS_PATH.read_text(encoding="utf-8"))
    return [
        Feed(
            name=item["name"],
            url=item["url"],
            max_items=item["maxItems"],
            exempt_hosts=frozenset(host.lower() for host in item.get("exemptHosts", [])),
        )
        for item in payload["feeds"]
    ]


def feed_document_id(url: str) -> str:
    return FEED_PREFIX + hashlib.sha256(url.encode("utf-8")).hexdigest()[:FEED_ID_LENGTH]


def _published_at(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        parsed = parsedate_to_datetime(raw.strip())
    except (TypeError, ValueError):
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def parse_feed(xml_text: str, max_items: int) -> list[FeedItem]:
    """RSS 2.0 items in feed order (newest first in practice); entries without an http(s) link are dropped."""
    root = ElementTree.fromstring(xml_text)
    items: list[FeedItem] = []
    for element in root.iter("item"):
        link = (element.findtext("link") or "").strip()
        if not link.startswith(HTTP_URL_SCHEMES):
            continue
        items.append(
            FeedItem(
                title=(element.findtext("title") or "").strip(),
                link=link,
                published_at=_published_at(element.findtext("pubDate")),
            )
        )
        if len(items) == max_items:
            break
    return items


async def _read_feed(client: httpx.AsyncClient, feed: Feed) -> list[FeedItem]:
    response = await client.get(feed.url, headers={"User-Agent": settings.corpus_fetch_user_agent})
    response.raise_for_status()
    if len(response.content) > settings.feeds_max_bytes:
        raise ValueError(f"feed larger than {settings.feeds_max_bytes} bytes")
    return parse_feed(response.text, feed.max_items)


async def _fetch_with_retry(client: httpx.AsyncClient, url: str) -> FetchedPage:
    for attempt in range(1, FETCH_ATTEMPTS + 1):
        try:
            return await fetch_page(client, url)
        except FetchError:
            if attempt == FETCH_ATTEMPTS:
                raise
            await asyncio.sleep(settings.feeds_retry_delay_seconds)
    raise AssertionError("unreachable: the last attempt returns or raises")


async def refresh_feeds(
    models: EmbeddingModels, store: VectorStore, transport: httpx.AsyncBaseTransport | None = None
) -> CorpusSyncState:
    """
    Reads the configured RSS feeds and indexes the entries the corpus does not have yet, through the normal ingest
    path (catalog, duplicates, chunking). The publication date comes from the feed, which states it explicitly.
    One unreachable feed or page never stops the run.
    """
    feeds = load_feeds()
    exempt_hosts = frozenset(host for feed in feeds for host in feed.exempt_hosts)

    async def load_pages(state: CorpusSyncState) -> list[Page]:
        pages: list[Page] = []
        async with httpx.AsyncClient(
            timeout=settings.corpus_fetch_timeout_seconds, follow_redirects=False, transport=transport
        ) as client:
            for feed in feeds:
                try:
                    items = await _read_feed(client, feed)
                except (httpx.HTTPError, ValueError, ElementTree.ParseError) as error:
                    state.failed += 1
                    logger.warning("Feed %s skipped (%s: %s)", feed.name, type(error).__name__, error)
                    continue
                for item in items:
                    document_id = feed_document_id(item.link)
                    if await db.active_chunk_ids_for_document(document_id):
                        state.already_present += 1
                        continue
                    try:
                        fetched = await _fetch_with_retry(client, item.link)
                    except FetchError as error:
                        state.failed += 1
                        logger.warning("Feed %s: %s skipped (%s)", feed.name, item.link, error)
                    else:
                        pages.append(
                            Page(
                                document_id=document_id,
                                url=fetched.url,
                                title=fetched.title or item.title,
                                content=fetched.text,
                                fetched_at=datetime.now(UTC),
                                published_at=item.published_at or fetched.published_at,
                            )
                        )
                    await asyncio.sleep(settings.corpus_fetch_delay_seconds)
        return pages

    return await run_corpus_job(
        feed_state, _feed_lock, "Feed refresh", load_pages, models, store, exempt_hosts=exempt_hosts
    )
