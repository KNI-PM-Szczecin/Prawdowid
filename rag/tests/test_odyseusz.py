import asyncio
from datetime import UTC, datetime

import httpx
import pytest

from app import db, odyseusz
from app.catalog import qualify
from app.config import settings
from app.corpus_sync import to_document
from app.ingest import content_hash
from app.odyseusz import (
    OdyseuszClient,
    OdyseuszError,
    build_page,
    country_page_url,
    odyseusz_document_id,
    parse_country_list,
    refresh_odyseusz,
    strip_markdown_links,
)

FETCHED_AT = datetime(2026, 11, 22, 8, 0, tzinfo=UTC)
NOTICE = (
    "W dniu 3 grudnia zapowiedziano fikcyjny festiwal latawców na terenie całego kraju.\n"
    "Szczegóły: [Program festiwalu](https://festiwal.example/program).\n"
    "Zalecamy:\n"
    "- śledź lokalne komunikaty;"
)
PROFILE = {"kodISO": "ES", "nazwa": "Hiszpania", "dataAktualizacji": "2026-11-20", "trescPowiadomieniaDluga": NOTICE}
WARNING = {
    "bazowyKodOstrzezenia": "ZACHOWAJ_ZWYKLA_OSTROZNOSC",
    "trescOstrzezeniaDlaKraju": "Oznacza poziom zagrożenia zbliżony do Polski.\n[Więcej](https://odyseusz.gov.pl/x)",
    "dataObowiazywaniaOd": "2026-11-19",
}


def test_markdown_links_keep_their_address_visible():
    assert strip_markdown_links("Zobacz [Program](https://a.example/p?x=1).") == (
        "Zobacz Program (https://a.example/p?x=1)."
    )


def test_page_starts_with_the_country_and_the_update_date_and_keeps_the_warning():
    page = build_page("ES", PROFILE, WARNING, FETCHED_AT)

    assert page.document_id == odyseusz_document_id("ES") == "odyseusz:ES"
    assert page.url == country_page_url("ES") == "https://odyseusz.gov.pl/ES"
    assert page.title == "Odyseusz (MSZ): Hiszpania - informacje dla podróżujących"
    assert page.content.startswith("Hiszpania (komunikat MSZ dla podróżujących, aktualizacja 2026-11-20):\n\nW dniu 3")
    assert "Program festiwalu (https://festiwal.example/program)" in page.content
    assert "\n\n- śledź lokalne komunikaty;" in page.content
    assert "obowiązuje od 2026-11-19): Oznacza poziom zagrożenia zbliżony do Polski." in page.content
    assert page.published_at == datetime(2026, 11, 20, tzinfo=UTC)
    assert page.fetched_at == FETCHED_AT
    source = qualify(to_document(page, page.content).source)
    assert (source.source_type, source.tier) == ("official", 1)


def test_no_notice_or_no_update_date_gives_no_document():
    assert build_page("ES", {**PROFILE, "trescPowiadomieniaDluga": "  "}, None, FETCHED_AT) is None
    assert build_page("ES", {**PROFILE, "dataAktualizacji": None}, None, FETCHED_AT) is None
    assert "Poziom ostrzeżenia" not in build_page("ES", PROFILE, None, FETCHED_AT).content


def test_country_list_keeps_valid_codes_only():
    payload = [{"kodIso": "ES", "nazwa": "Hiszpania"}, {"kodIso": "../x", "nazwa": "Zła"}, {"kodIso": "FR"}, "x"]
    assert [country.iso for country in parse_country_list(payload)] == ["ES"]
    with pytest.raises(OdyseuszError):
        parse_country_list({"not": "a list"})


COUNTRIES = [
    {"kodIso": "ES", "nazwa": "Hiszpania"},
    {"kodIso": "PT", "nazwa": "Portugalia"},
    {"kodIso": "FR", "nazwa": "Francja"},
    {"kodIso": "GR", "nazwa": "Grecja"},
]


def _transport(calls: list[str]) -> httpx.MockTransport:
    profiles = {
        "ES": PROFILE,
        "PT": {**PROFILE, "kodISO": "PT", "nazwa": "Portugalia", "trescPowiadomieniaDluga": "Bez zmian od wczoraj."},
        "FR": {**PROFILE, "kodISO": "FR", "nazwa": "Francja", "trescPowiadomieniaDluga": None},
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/api/v1/informacje/")
        calls.append(path)
        if path == "profile-panstw/mini":
            return httpx.Response(200, json=COUNTRIES)
        if path.endswith("/ostrzezenia"):
            return httpx.Response(200, json=WARNING)
        iso = path.removeprefix("profile-panstw/")
        if iso in profiles:
            return httpx.Response(200, json=profiles[iso])
        return httpx.Response(500)

    return httpx.MockTransport(handler)


@pytest.fixture
def corpus(monkeypatch):
    state = {"hashes": {}, "fetched_at": {}, "ingested": [], "deleted": [], "near_duplicate_allowed": []}

    async def ingest_document(document, models, store, allow_near_duplicate=False):
        qualify(document.source)
        state["ingested"].append(document)
        state["near_duplicate_allowed"].append(allow_near_duplicate)

    async def delete_document_chunks(document_id, store):
        state["deleted"].append(document_id)
        return 2

    async def document_content_hash(document_id):
        return state["hashes"].get(document_id)

    async def document_fetched_at(document_id):
        return state["fetched_at"].get(document_id)

    monkeypatch.setattr("app.corpus_sync.ingest_document", ingest_document)
    monkeypatch.setattr(odyseusz, "ingest_document", ingest_document)
    monkeypatch.setattr(odyseusz, "delete_document_chunks", delete_document_chunks)
    monkeypatch.setattr(db, "document_content_hash", document_content_hash)
    monkeypatch.setattr(db, "document_fetched_at", document_fetched_at)
    monkeypatch.setattr(settings, "odyseusz_request_delay_seconds", 0)
    odyseusz.odyseusz_state.reset(running=False)
    return state


def test_refresh_indexes_new_notices_skips_unchanged_and_removes_withdrawn(corpus):
    unchanged = asyncio.run(_page_for("PT"))
    corpus["hashes"]["odyseusz:PT"] = content_hash(unchanged.content)
    calls: list[str] = []

    state = asyncio.run(refresh_odyseusz(models=None, store=None, transport=_transport(calls)))

    assert [document.source.document_id for document in corpus["ingested"]] == ["odyseusz:ES"]
    assert corpus["deleted"] == ["odyseusz:FR"]
    assert (state.indexed, state.already_present, state.failed) == (1, 1, 1)
    assert state.last_error is None
    assert "FR/ostrzezenia" not in calls
    assert corpus["near_duplicate_allowed"] == [True]


async def _page_for(iso: str):
    async with httpx.AsyncClient(transport=_transport([])) as client:
        return await odyseusz.fetch_country_page(client, iso, FETCHED_AT)


def test_refresh_reports_an_unavailable_country_list(corpus):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    state = asyncio.run(refresh_odyseusz(models=None, store=None, transport=httpx.MockTransport(handler)))
    assert state.last_error is not None and corpus["ingested"] == []


def _fill(claim: str, calls: list[str]):
    async def run():
        client = OdyseuszClient(transport=_transport(calls))
        try:
            return await client.fill(claim, models=None, store=None)
        finally:
            await client.close()

    return asyncio.run(run())


def test_a_claim_naming_a_country_fetches_and_indexes_its_notice(corpus):
    calls: list[str] = []
    result = _fill("Czy w Hiszpanii odbędzie się festiwal latawców?", calls)

    assert (result.status, result.indexed) == ("ok", 1)
    assert calls == ["profile-panstw/ES", "ES/ostrzezenia"]
    assert corpus["ingested"][0].source.document_id == "odyseusz:ES"
    assert corpus["near_duplicate_allowed"] == [True]


def test_on_demand_fetch_runs_while_the_scheduled_refresh_holds_its_lock(corpus):
    calls: list[str] = []

    async def run():
        async with odyseusz._refresh_lock:
            client = OdyseuszClient(transport=_transport(calls))
            try:
                return await client.fill("Czy w Hiszpanii odbędzie się festiwal latawców?", models=None, store=None)
            finally:
                await client.close()

    result = asyncio.run(run())
    assert (result.status, result.indexed) == ("ok", 1)


def test_no_country_or_a_fresh_copy_means_no_request(corpus):
    calls: list[str] = []
    assert _fill("Czy festiwal latawców się odbędzie?", calls).status == "skipped"
    corpus["fetched_at"]["odyseusz:ES"] = datetime.now(UTC)
    assert _fill("Czy w Hiszpanii odbędzie się festiwal?", calls).indexed == 0
    assert calls == []
