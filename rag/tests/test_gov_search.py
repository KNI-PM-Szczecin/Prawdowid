import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest

from app import db, gov_search
from app.catalog import qualify
from app.config import settings
from app.corpus_sync import web_document_id
from app.gov_search import GovSearchClient, GovSearchHit, parse_hits, select_hits, wanted
from app.models import Passage, SearchFilters, SearchRequest

OLD_PAGE = "/web/gov/uzyskaj-zasilek"
NEW_PAGE = "/web/rodzina/zasilek-z-wyzsza-kwota"
OTHER_PAGE = "/web/gov/inny-zasilek"
SEARCH_PAYLOAD = {
    "count": 3,
    "results": [
        {"title": "Uzyskaj zasiłek", "url": OLD_PAGE, "publishDate": "2019-09-20T13:03:02.957Z"},
        {"title": "Inny zasiłek", "url": OTHER_PAGE, "publishDate": "2021-12-29T09:25:20.652Z"},
        {"title": "Zasiłek z wyższą kwotą", "url": NEW_PAGE, "publishDate": "2026-04-07T11:42:29.836Z"},
        {"title": "Bez daty", "url": "/web/gov/bez-daty", "publishDate": None},
    ],
}


def _hit(path: str, year: int) -> GovSearchHit:
    return GovSearchHit(title=path, url=f"https://www.gov.pl{path}", published_at=datetime(year, 1, 1, tzinfo=UTC))


def test_parse_hits_drops_undated_and_builds_absolute_urls():
    hits = parse_hits(SEARCH_PAYLOAD)
    assert [hit.url for hit in hits] == [f"https://www.gov.pl{path}" for path in (OLD_PAGE, OTHER_PAGE, NEW_PAGE)]
    assert hits[2].published_at == datetime(2026, 4, 7, 11, 42, 29, 836000, tzinfo=UTC)


def test_select_hits_keeps_best_match_and_adds_newest():
    hits = [_hit("/best", 2019), _hit("/old", 2015), _hit("/newest", 2026), _hit("/newer", 2024)]
    assert [hit.title for hit in select_hits(hits, 3)] == ["/best", "/newest", "/newer"]
    assert select_hits([], 3) == []


def _passage(score: float) -> Passage:
    return Passage(
        document_id="doc",
        title="t",
        publisher="p",
        published_at=None,
        fetched_at=datetime(2026, 1, 1, tzinfo=UTC),
        url="https://www.gov.pl/x",
        license=None,
        source_type="official",
        passage="tekst",
        score=score,
        flags=[],
        chunk_id=uuid4(),
        tier=1,
        reliability="high",
    )


def test_wanted_only_without_enough_results_and_when_official_sources_allowed():
    plain = SearchRequest(query="Zasiłek pogrzebowy wynosi 4000 zł.")
    clear_match, weak_match = _passage(0.8), _passage(settings.gov_search_sufficient_score - 0.1)
    assert wanted(plain, [])
    assert not wanted(plain, [clear_match])
    assert wanted(plain, [weak_match])
    assert not wanted(plain, [weak_match, clear_match])
    factcheck_only = SearchRequest(query="x y z", filters=SearchFilters(source_types=["factcheck"]))
    assert not wanted(factcheck_only, [])


@pytest.fixture
def corpus(monkeypatch):
    """Fake corpus state: when each document was fetched, which have active chunks, what was ingested or deleted."""
    state = {"fetched_at": {}, "ingested": [], "deleted": []}

    async def document_fetched_at(document_id):
        return state["fetched_at"].get(document_id)

    async def active_chunk_ids_for_document(document_id):
        return ["chunk"] if document_id in state["fetched_at"] else []

    async def ingest_document(document, models, store):
        qualify(document.source)
        state["ingested"].append(document)

    async def delete_document_chunks(document_id, store):
        state["deleted"].append(document_id)
        return 1

    monkeypatch.setattr(db, "document_fetched_at", document_fetched_at)
    monkeypatch.setattr(db, "active_chunk_ids_for_document", active_chunk_ids_for_document)
    monkeypatch.setattr(gov_search, "ingest_document", ingest_document)
    monkeypatch.setattr(gov_search, "delete_document_chunks", delete_document_chunks)
    return state


def _transport(search_status: int = 200, delay: float = 0.0) -> httpx.MockTransport:
    async def handler(request: httpx.Request) -> httpx.Response:
        if delay:
            await asyncio.sleep(delay)
        if request.url.path == "/api/data/search":
            return httpx.Response(search_status, json=SEARCH_PAYLOAD)
        path = request.url.path
        body = f"<html><head><title>{path}</title></head><body><p>Treść {path}.</p></body></html>"
        return httpx.Response(200, text=body, headers={"content-type": "text/html"})

    return httpx.MockTransport(handler)


def _fill(client: GovSearchClient, query: str = "Zasiłek pogrzebowy wynosi 4000 zł."):
    async def run():
        try:
            return await client.fill(query, models=None, store=None)
        finally:
            await client.close()

    return asyncio.run(run())


def test_fill_indexes_best_and_newest_pages_with_gov_publication_dates(corpus, monkeypatch):
    monkeypatch.setattr(settings, "gov_search_max_pages", 2)
    result = _fill(GovSearchClient(transport=_transport()))

    assert (result.status, result.indexed) == ("ok", 2)
    sources = [document.source for document in corpus["ingested"]]
    assert [str(source.url) for source in sources] == [f"https://www.gov.pl{OLD_PAGE}", f"https://www.gov.pl{NEW_PAGE}"]
    assert [source.published_at.year for source in sources] == [2019, 2026]
    assert sources[0].document_id == web_document_id(f"https://www.gov.pl{OLD_PAGE}")
    assert corpus["deleted"] == []


def test_fill_skips_recent_copy_and_refreshes_stale_one(corpus, monkeypatch):
    monkeypatch.setattr(settings, "gov_search_max_pages", 2)
    now = datetime.now(UTC)
    recent_id = web_document_id(f"https://www.gov.pl{OLD_PAGE}")
    stale_id = web_document_id(f"https://www.gov.pl{NEW_PAGE}")
    corpus["fetched_at"][recent_id] = now - timedelta(days=1)
    corpus["fetched_at"][stale_id] = now - timedelta(days=settings.gov_search_refresh_days + 1)

    result = _fill(GovSearchClient(transport=_transport()))

    assert result.indexed == 1
    assert [document.source.document_id for document in corpus["ingested"]] == [stale_id]
    assert corpus["deleted"] == [stale_id]


def test_search_failure_is_reported_not_raised(corpus):
    result = _fill(GovSearchClient(transport=_transport(search_status=503)))
    assert (result.status, result.indexed) == ("error", 0)
    assert corpus["ingested"] == []


def test_disabled_source_does_nothing(corpus, monkeypatch):
    monkeypatch.setattr(settings, "gov_search_enabled", False)
    result = _fill(GovSearchClient(transport=_transport()))
    assert (result.status, result.indexed) == ("disabled", 0)


def test_slow_fill_returns_within_budget(corpus, monkeypatch):
    monkeypatch.setattr(settings, "gov_search_budget_seconds", 0.05)
    result = _fill(GovSearchClient(transport=_transport(delay=0.5)))
    assert (result.status, result.indexed) == ("ok", 0)
