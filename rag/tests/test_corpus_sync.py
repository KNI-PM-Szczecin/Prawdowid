import asyncio

import pytest

from app import corpus_sync, db
from app.config import settings
from app.corpus_sync import ScrapedPage, parse_date_code, remove_boilerplate, sync_corpus, to_document
from app.ingest import DuplicateDocumentError

NAV = "Przejdź do menu głównego"
PAGES = [
    ScrapedPage(
        1,
        20261116,
        "https://www.gov.pl/web/mswia/rso",
        "Strefa buforowa",
        f"{NAV}\nStrefa przedłużona do 2027.\nStopka",
    ),
    ScrapedPage(
        2, 20261117, "https://policja.pl/pol/aktualnosci", "Aktualności", f"{NAV}\nZatrzymano 3 osoby.\nStopka"
    ),
    ScrapedPage(3, 20261118, "https://kgsok.pl/", "SOK", f"{NAV}\nKontrola na dworcu.\nStopka"),
    ScrapedPage(4, 20261118, "https://kgsok.pl/", "SOK kopia", f"{NAV}\nKontrola na dworcu.\nStopka"),
    ScrapedPage(5, None, "https://blog.example.net/x", "Spoza katalogu", "Tekst spoza katalogu."),
]


def test_parse_date_code_accepts_only_yyyymmdd():
    assert parse_date_code(20261116).date().isoformat() == "2026-11-16"
    assert parse_date_code(20261399) is None
    assert parse_date_code(1794787200) is None
    assert parse_date_code(None) is None


def test_boilerplate_lines_are_dropped_and_lines_become_paragraphs():
    cleaned = remove_boilerplate([page.content for page in PAGES], share=0.3, min_documents=3)
    assert cleaned[0] == "Strefa przedłużona do 2027."
    assert NAV not in cleaned[1] and "Stopka" not in cleaned[1]
    assert remove_boilerplate(["a\nb", "a\nb"], share=0.3, min_documents=3) == ["a\n\nb", "a\n\nb"]


def test_to_document_uses_catalog_publisher_and_scrape_date():
    document = to_document(PAGES[0], "Strefa przedłużona do 2027.")
    assert document.source.document_id == "scrapped:1"
    assert document.source.publisher.startswith("Administracja rządowa")
    assert document.source.fetched_at.date().isoformat() == "2026-11-16"
    assert document.source.published_at is None
    assert document.source.topic_tag == "www.gov.pl"
    assert to_document(PAGES[4], "x").source.publisher == "blog.example.net"


def test_sync_counts_indexed_duplicates_outside_and_continues(monkeypatch):
    seen_hashes: dict[str, str] = {}

    async def fetch_scraped_pages(limit):
        return [
            {"id": p.row_id, "date": p.date_code, "site": p.site, "title": p.title, "content": p.content} for p in PAGES
        ]

    async def ingest_document(document, models, store):
        from app.ingest import content_hash

        digest = content_hash(document.text)
        if digest in seen_hashes:
            raise DuplicateDocumentError(document.source.document_id, seen_hashes[digest])
        seen_hashes[digest] = document.source.document_id
        from app.catalog import qualify

        qualify(document.source)

    monkeypatch.setattr(db, "fetch_scraped_pages", fetch_scraped_pages)
    monkeypatch.setattr(corpus_sync, "ingest_document", ingest_document)
    monkeypatch.setattr(settings, "corpus_boilerplate_min_documents", 3)
    corpus_sync.sync_state.__init__()

    state = asyncio.run(sync_corpus(models=None, store=None, max_documents=100))

    assert (state.indexed, state.skipped_duplicates, state.skipped_outside_catalog, state.failed) == (3, 1, 1, 0)
    assert state.available == len(PAGES)
    assert state.last_error is None and state.running is False


def test_invalid_table_name_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "corpus_scraped_table", 'Scrapped"; DROP TABLE x;--')
    with pytest.raises(ValueError):
        asyncio.run(db.fetch_scraped_pages(1))
