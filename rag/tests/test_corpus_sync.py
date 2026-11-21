import asyncio
from datetime import UTC, datetime

import httpx
import pytest

from app import corpus_sync, db
from app.catalog import qualify
from app.config import settings
from app.corpus_sync import (
    Page,
    fetch_corpus,
    parse_date_code,
    remove_boilerplate,
    seed_published_at,
    seed_urls,
    sync_corpus,
    to_document,
    web_document_id,
)
from app.ingest import DuplicateDocumentError, content_hash

NAV = "Przejdź do menu głównego"
NOW = datetime(2026, 11, 21, tzinfo=UTC)
PAGES = [
    Page(
        "scrapped:1", "https://www.gov.pl/web/mswia/rso", "Strefa buforowa", f"{NAV}\nStrefa przedłużona.\nStopka", NOW
    ),
    Page("scrapped:2", "https://policja.pl/pol/aktualnosci", "Aktualności", f"{NAV}\nZatrzymano 3 osoby.\nStopka", NOW),
    Page("scrapped:3", "https://kgsok.pl/", "SOK", f"{NAV}\nKontrola na dworcu.\nStopka", NOW),
    Page("scrapped:4", "https://kgsok.pl/", "SOK kopia", f"{NAV}\nKontrola na dworcu.\nStopka", NOW),
    Page("scrapped:5", "https://blog.example.net/x", "Spoza katalogu", "Tekst spoza katalogu.", NOW),
]


@pytest.fixture
def fake_ingest(monkeypatch):
    seen_hashes: dict[str, str] = {}
    ingested: list[str] = []

    async def ingest_document(document, models, store):
        digest = content_hash(document.text)
        if digest in seen_hashes:
            raise DuplicateDocumentError(document.source.document_id, seen_hashes[digest])
        qualify(document.source)
        seen_hashes[digest] = document.source.document_id
        ingested.append(document.source.document_id)

    monkeypatch.setattr(corpus_sync, "ingest_document", ingest_document)
    monkeypatch.setattr(settings, "corpus_boilerplate_min_documents", 3)
    monkeypatch.setattr(settings, "corpus_fetch_delay_seconds", 0)
    corpus_sync.sync_state.__init__()
    corpus_sync.fetch_state.__init__()
    return ingested


def test_parse_date_code_accepts_only_yyyymmdd():
    assert parse_date_code(20261116).date().isoformat() == "2026-11-16"
    assert parse_date_code(20261399) is None
    assert parse_date_code(1794787200) is None
    assert parse_date_code(None) is None


def test_boilerplate_lines_are_dropped_and_lines_become_paragraphs():
    cleaned = remove_boilerplate([page.content for page in PAGES], share=0.3, min_documents=3)
    assert cleaned[0] == "Strefa przedłużona."
    assert NAV not in cleaned[1] and "Stopka" not in cleaned[1]
    assert remove_boilerplate(["a\nb", "a\nb"], share=0.3, min_documents=3) == ["a\n\nb", "a\n\nb"]


def test_to_document_uses_catalog_publisher_and_host_topic():
    document = to_document(PAGES[0], "Strefa przedłużona.")
    assert document.source.document_id == "scrapped:1"
    assert document.source.publisher.startswith("Administracja rządowa")
    assert document.source.fetched_at == NOW
    assert document.source.published_at is None
    assert document.source.topic_tag == "www.gov.pl"
    assert to_document(PAGES[4], "x").source.publisher == "blog.example.net"


def test_to_document_keeps_publication_date_from_the_page():
    page = Page(
        "web:1",
        "https://www.gov.pl/web/rcb/a",
        "Komunikat",
        "Treść.",
        NOW,
        published_at=datetime(2024, 3, 12, tzinfo=UTC),
    )
    assert to_document(page, "Treść.").source.published_at == datetime(2024, 3, 12, tzinfo=UTC)


def test_sync_counts_indexed_duplicates_outside_and_continues(fake_ingest, monkeypatch):
    async def fetch_scraped_pages(limit):
        return [
            {"id": index + 1, "date": 20261116, "site": page.url, "title": page.title, "content": page.content}
            for index, page in enumerate(PAGES)
        ]

    monkeypatch.setattr(db, "fetch_scraped_pages", fetch_scraped_pages)
    state = asyncio.run(sync_corpus(models=None, store=None, max_documents=100))

    assert (state.indexed, state.skipped_duplicates, state.skipped_outside_catalog, state.failed) == (3, 1, 1, 0)
    assert state.available == len(PAGES)
    assert state.last_error is None and state.running is False
    assert fake_ingest == ["scrapped:1", "scrapped:2", "scrapped:3"]


def test_fetch_indexes_html_pages_and_counts_failures(fake_ingest):
    urls = [
        "https://www.gov.pl/web/rcb/a",
        "https://www.gov.pl/web/rcb/b",
        "https://www.gov.pl/pdf",
        "https://demagog.org.pl/x",
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/pdf"):
            return httpx.Response(200, content=b"%PDF", headers={"content-type": "application/pdf"})
        if path.endswith("/b"):
            return httpx.Response(503)
        body = (
            f"<html><head><title>Strona {path}</title></head><body><p>Treść strony {path} o alercie.</p></body></html>"
        )
        return httpx.Response(200, text=body, headers={"content-type": "text/html"})

    state = asyncio.run(fetch_corpus(urls, models=None, store=None, transport=httpx.MockTransport(handler)))

    assert (state.indexed, state.failed, state.skipped_duplicates, state.skipped_outside_catalog) == (2, 2, 0, 0)
    assert state.available == 2
    assert fake_ingest == [web_document_id(urls[0]), web_document_id(urls[3])]


def test_seed_urls_are_all_in_catalog_domains():
    from app.catalog import resolve_entry

    urls = seed_urls()
    assert len(urls) >= 30
    assert all(resolve_entry(url) is not None for url in urls)


def test_seed_published_at_returns_only_pinned_iso_dates():
    assert seed_published_at("https://www.gov.pl/web/premier/25-lat-temu-polska-przystapila-do-nato") is not None
    assert seed_published_at("https://example.org/bez-daty") is None


def test_invalid_table_name_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "corpus_scraped_table", 'Scrapped"; DROP TABLE x;--')
    with pytest.raises(ValueError):
        asyncio.run(db.fetch_scraped_pages(1))
