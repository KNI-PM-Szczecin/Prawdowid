import asyncio

import httpx
import pytest

from app import corpus_sync, db, feeds, fetcher
from app.catalog import qualify
from app.config import settings
from app.corpus_rules import exclusion_reason
from app.feeds import feed_document_id, parse_feed, refresh_feeds

FEED_URL = "https://www.policja.pl/dokumenty/rss/1-rss-1.rss"
NEW_ARTICLE = "https://policja.pl/pol/aktualnosci/284200,Komunikat-w-sprawie-sprawcy.html"
OLD_ARTICLE = "https://policja.pl/pol/aktualnosci/284100,Wczesniejszy-komunikat.html"
LISTING = "https://policja.pl/pol/aktualnosci"


def _item(title: str, link: str | None, published: str) -> str:
    link_tag = f"<link>{link}</link>" if link else ""
    return f"<item><title>{title}</title>{link_tag}<pubDate>{published}</pubDate></item>"


RSS = (
    '<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>Policja</title>'
    + _item("Komunikat w sprawie sprawcy", NEW_ARTICLE, "Sat, 21 Nov 2026 08:00:00 +0100")
    + _item("Wcześniejszy komunikat", OLD_ARTICLE, "Fri, 20 Nov 2026 08:00:00 +0100")
    + _item("Lista aktualności", LISTING, "Fri, 20 Nov 2026 07:00:00 +0100")
    + _item("Bez linku", None, "Fri, 20 Nov 2026 06:00:00 +0100")
    + _item("Zła data", "https://policja.pl/pol/aktualnosci/1,x.html", "wczoraj")
    + "</channel></rss>"
)


def test_parse_feed_reads_links_and_dates_and_drops_entries_without_a_link():
    items = parse_feed(RSS, 10)
    assert [item.link for item in items] == [
        NEW_ARTICLE,
        OLD_ARTICLE,
        LISTING,
        "https://policja.pl/pol/aktualnosci/1,x.html",
    ]
    assert items[0].published_at.isoformat() == "2026-11-21T08:00:00+01:00"
    assert items[-1].published_at is None
    assert len(parse_feed(RSS, 2)) == 2


def test_the_host_exclusion_is_lifted_only_for_exempt_hosts_and_address_rules_stay():
    assert exclusion_reason(NEW_ARTICLE, "Komunikat") is not None
    assert exclusion_reason(NEW_ARTICLE, "Komunikat", frozenset({"policja.pl"})) is None
    assert exclusion_reason(LISTING, "Aktualności", frozenset({"policja.pl"})) is not None


@pytest.fixture
def ingested(monkeypatch):
    documents = {}

    async def ingest_document(document, models, store):
        qualify(document.source)
        documents[document.source.document_id] = document

    async def active_chunks(document_id):
        return ["present"] if document_id == feed_document_id(OLD_ARTICLE) else []

    async def allow(url):
        return None

    monkeypatch.setattr(corpus_sync, "ingest_document", ingest_document)
    monkeypatch.setattr(db, "active_chunk_ids_for_document", active_chunks)
    monkeypatch.setattr(fetcher, "assert_public_url", allow)
    monkeypatch.setattr(settings, "corpus_fetch_delay_seconds", 0)
    monkeypatch.setattr(
        feeds,
        "load_feeds",
        lambda: [feeds.Feed("Policja", FEED_URL, 15, frozenset({"policja.pl"}))],
    )
    feeds.feed_state.reset(running=False)
    return documents


def _transport(failing_feed: bool = False) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == FEED_URL:
            return httpx.Response(503) if failing_feed else httpx.Response(200, text=RSS)
        body = (
            f"<html><head><title>Strona</title></head><body><p>Treść komunikatu {request.url.path}.</p></body></html>"
        )
        return httpx.Response(200, text=body, headers={"content-type": "text/html"})

    return httpx.MockTransport(handler)


def test_refresh_indexes_only_new_entries_with_the_date_from_the_feed(ingested):
    state = asyncio.run(refresh_feeds(models=None, store=None, transport=_transport()))
    new_id = feed_document_id(NEW_ARTICLE)
    assert new_id.startswith("feed:")
    assert new_id in ingested
    assert feed_document_id(OLD_ARTICLE) not in ingested  # already in the corpus
    assert feed_document_id(LISTING) not in ingested  # a list page is not evidence, whatever the feed says
    assert ingested[new_id].source.published_at.isoformat() == "2026-11-21T08:00:00+01:00"
    assert ingested[new_id].source.publisher == "Policja"
    assert state.already_present == 1
    assert state.skipped_excluded == 1
    assert state.last_error is None and state.running is False


def test_an_unreachable_feed_is_counted_and_never_stops_the_run(ingested):
    state = asyncio.run(refresh_feeds(models=None, store=None, transport=_transport(failing_feed=True)))
    assert ingested == {}
    assert state.failed == 1
    assert state.last_error is None
