import asyncio
import json

import httpx
import pytest

from app import euvsdisinfo
from app.config import settings
from app.euvsdisinfo import EuvsDisinfoClient, EuvsDisinfoError, parse_case, sync_cases

TOKEN = "test-euvsdisinfo-token"
TOTAL_CASES = 5
PAGE_SIZE = 2

RAW_CASE = {
    "id": "case-1",
    "title": "Europe is going bankrupt because of Ukraine",
    "claim": "<p>Support for Ukraine is ruining Europe&#8217;s economy.</p>",
    "fact": "<p>There is no evidence.</p>",
    "date": 1794787200,
    "keywords": [{"_id": "k1", "title": "War against Ukraine"}],
    "countries": [{"_id": "c1", "title": "Europe"}, {"_id": "c2", "title": "Poland"}],
    "linksToDisinformation": [
        {"language": {"name": "Russian", "id": "rus"}, "url": "https://example.org/a"},
        {"language": {"name": "Russian", "id": "rus"}, "url": "https://example.org/b"},
        {"language": None, "url": "https://example.org/c"},
    ],
    "url": "https://euvsdisinfo.eu/report/case-1",
}


def _cases_response(offset: int, limit: int, sse: bool = True) -> httpx.Response:
    cases = [{**RAW_CASE, "id": f"case-{index}"} for index in range(offset, min(offset + limit, TOTAL_CASES))]
    payload = {"jsonrpc": "2.0", "id": offset, "result": {"structuredContent": {"total": TOTAL_CASES, "cases": cases}}}
    if sse:
        return httpx.Response(
            200, text=f"event: message\ndata: {json.dumps(payload)}\n\n", headers={"content-type": "text/event-stream"}
        )
    return httpx.Response(200, json=payload)


class FakeIncidentStore:
    def __init__(self):
        self.points = {}

    async def upsert_raw(self, points):
        for point in points:
            self.points[point.point_id] = point


class FakeModels:
    def embed_documents(self, texts):
        return [[0.0]] * len(texts), [None] * len(texts)


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setattr(settings, "euvsdisinfo_token", TOKEN)
    monkeypatch.setattr(settings, "euvsdisinfo_page_size", PAGE_SIZE)
    euvsdisinfo.sync_state.__init__()


def test_parse_case_strips_html_and_maps_fields():
    incident = parse_case(RAW_CASE)
    assert incident.incident_id == "case-1"
    assert incident.source == "euvsdisinfo"
    assert incident.summary == "Support for Ukraine is ruining Europe\N{RIGHT SINGLE QUOTATION MARK}s economy."
    assert incident.countries == ["Europe", "Poland"]
    assert incident.languages == ["Russian"]
    assert incident.published_at.year == 2026


def test_parse_case_skips_records_without_claim_or_url():
    assert parse_case({**RAW_CASE, "claim": "<p> </p>"}) is None
    assert parse_case({key: value for key, value in RAW_CASE.items() if key != "url"}) is None


def test_fetch_cases_sends_bearer_header_and_reads_sse():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        arguments = json.loads(request.content)["params"]["arguments"]
        return _cases_response(arguments["offset"], arguments["limit"])

    page = asyncio.run(EuvsDisinfoClient(transport=httpx.MockTransport(handler)).fetch_cases(2, 0))
    request = requests[0]
    assert page.total == TOTAL_CASES
    assert [incident.incident_id for incident in page.incidents] == ["case-0", "case-1"]
    assert request.headers["Authorization"] == f"Bearer {TOKEN}"
    assert TOKEN not in str(request.url)
    assert request.headers["Accept"] == "application/json, text/event-stream"
    assert json.loads(request.content)["params"]["name"] == "cases"


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(401, json={"jsonrpc": "2.0", "error": {"code": -32001}}),
        httpx.Response(200, json={"jsonrpc": "2.0", "id": 0, "error": {"code": -32603, "message": "boom"}}),
        httpx.Response(200, json={"jsonrpc": "2.0", "id": 0, "result": {"content": []}}),
    ],
)
def test_fetch_cases_raises_explicit_error(response):
    client = EuvsDisinfoClient(transport=httpx.MockTransport(lambda request: response))
    with pytest.raises(EuvsDisinfoError):
        asyncio.run(client.fetch_cases(2, 0))


def test_sync_pages_until_total_and_is_idempotent():
    def handler(request: httpx.Request) -> httpx.Response:
        arguments = json.loads(request.content)["params"]["arguments"]
        return _cases_response(arguments["offset"], arguments["limit"], sse=False)

    client = EuvsDisinfoClient(transport=httpx.MockTransport(handler))
    store = FakeIncidentStore()
    state = asyncio.run(sync_cases(client, FakeModels(), store, max_cases=100))
    asyncio.run(sync_cases(client, FakeModels(), store, max_cases=100))

    assert state.last_indexed == TOTAL_CASES
    assert state.available == TOTAL_CASES
    assert state.last_error is None
    assert len(store.points) == TOTAL_CASES


def test_sync_respects_max_cases_and_records_failure():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        arguments = json.loads(request.content)["params"]["arguments"]
        calls.append(arguments)
        if arguments["offset"] >= PAGE_SIZE:
            return httpx.Response(500)
        return _cases_response(arguments["offset"], arguments["limit"])

    client = EuvsDisinfoClient(transport=httpx.MockTransport(handler))
    store = FakeIncidentStore()
    state = asyncio.run(sync_cases(client, FakeModels(), store, max_cases=3))

    assert calls == [{"limit": 2, "offset": 0}, {"limit": 1, "offset": 2}]
    assert state.last_indexed == PAGE_SIZE
    assert "HTTP 500" in state.last_error
    assert not state.running


def test_sync_stops_on_page_shorter_than_requested():
    """A server-side page-size cap must not skip cases nor loop: offset advances by what arrived, not by the request."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        arguments = json.loads(request.content)["params"]["arguments"]
        calls.append(arguments)
        # Server caps every page at one case and reports no total.
        return _cases_response(arguments["offset"], 1, sse=False)

    client = EuvsDisinfoClient(transport=httpx.MockTransport(handler))
    state = asyncio.run(sync_cases(client, FakeModels(), FakeIncidentStore(), max_cases=10))

    assert len(calls) == 1
    assert state.last_indexed == 1
    assert state.last_error is None
