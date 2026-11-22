import asyncio

import httpx

from app.config import settings
from app.wikidata import WikidataClient, format_time, parse_people, person_mentions

PERSON_ID = "Q100"
NAMESAKE_ID = "Q200"
WORK_ID = "Q300"


def _entity(entity_id: str, label: str, human: bool, died: str | None = None, description: str | None = None) -> dict:
    claims: dict = {"P31": [{"mainsnak": {"datavalue": {"value": {"id": "Q5" if human else "Q11424"}}}}]}
    claims["P569"] = [{"mainsnak": {"datavalue": {"value": {"time": "+1930-04-21T00:00:00Z", "precision": 11}}}}]
    if died:
        claims["P570"] = [{"mainsnak": {"datavalue": {"value": {"time": died, "precision": 11}}}}]
    return {
        "labels": {"pl": {"value": label}},
        "descriptions": {"pl": {"value": description}} if description else {},
        "claims": claims,
        "modified": "2026-11-01T10:00:00Z",
    }


ENTITIES = {
    WORK_ID: _entity(WORK_ID, "Królowa Zofia", human=False, description="serial telewizyjny"),
    PERSON_ID: _entity(
        PERSON_ID, "Zofia I", human=True, died="+2021-03-05T00:00:00Z", description="królowa Borowii w latach 1950-2021"
    ),
    NAMESAKE_ID: _entity(NAMESAKE_ID, "Zofia z Borowa", human=True),
}


def _transport(calls: list[dict]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        calls.append(params)
        if params["action"] == "wbsearchentities":
            return httpx.Response(200, json={"search": [{"id": WORK_ID}, {"id": PERSON_ID}, {"id": NAMESAKE_ID}]})
        ids = params["ids"].split("|")
        return httpx.Response(200, json={"entities": {entity_id: ENTITIES[entity_id] for entity_id in ids}})

    return httpx.MockTransport(handler)


def test_person_mentions_keep_titles_and_full_names():
    assert person_mentions("Królowa Zofia odwiedziła Sejm w ostatni piątek.") == ["Królowa Zofia", "Sejm"]
    assert person_mentions("wszystko małymi literami") == []


def test_format_time_by_precision():
    assert format_time({"time": "+2021-03-05T00:00:00Z", "precision": 11}) == "5 marca 2021 r."
    assert format_time({"time": "+1480-00-00T00:00:00Z", "precision": 9}) == "1480 r."
    assert format_time({"time": "bad"}) is None


def test_parse_people_keeps_humans_with_polish_labels():
    facts = parse_people(ENTITIES)
    assert [fact.entity_id for fact in facts] == [PERSON_ID, NAMESAKE_ID]
    assert "Data śmierci: 5 marca 2021 r." in facts[0].passage_text
    assert "W danych nie ma daty śmierci." in facts[1].passage_text


def test_first_human_in_search_order_is_the_person_meant(monkeypatch):
    monkeypatch.setattr(settings, "wikidata_enabled", True)
    calls: list[dict] = []
    client = WikidataClient(transport=_transport(calls))
    result = asyncio.run(client.people("Królowa Zofia odwiedziła most."))

    assert result.status == "ok"
    assert [fact.entity_id for fact in result.facts] == [PERSON_ID]
    assert result.facts[0].url == "https://www.wikidata.org/wiki/Q100"
    assert calls[0]["search"] == "Królowa Zofia"


def test_no_names_or_disabled_means_no_request(monkeypatch):
    calls: list[dict] = []
    client = WikidataClient(transport=_transport(calls))
    assert asyncio.run(client.people("bez nazw własnych")).status == "skipped"
    monkeypatch.setattr(settings, "wikidata_enabled", False)
    assert asyncio.run(client.people("Królowa Zofia")).status == "disabled"
    assert calls == []


def test_failure_is_an_error_status_not_an_exception(monkeypatch):
    monkeypatch.setattr(settings, "wikidata_enabled", True)
    client = WikidataClient(transport=httpx.MockTransport(lambda request: httpx.Response(503)))
    result = asyncio.run(client.people("Królowa Zofia odwiedziła most."))
    assert (result.status, result.facts) == ("error", [])
