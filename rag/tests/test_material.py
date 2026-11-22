from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app import db, material
from app.main import app
from app.urls import normalize_url

PUBLISHED = datetime(2026, 11, 20, 10, 0, tzinfo=UTC)


class FakeIncidents:
    def __init__(self, payloads: list[dict]) -> None:
        self.payloads = payloads

    async def find_by_payload(self, field: str, value: str, limit: int) -> list[dict]:
        return [payload for payload in self.payloads if value in payload.get(field, [])][:limit]


def source_row(url: str, title: str, published_at: datetime | None = PUBLISHED) -> dict:
    return {
        "document_id": "web:" + url,
        "title": title,
        "publisher": "PAP",
        "url": url,
        "published_at": published_at,
        "fetched_at": PUBLISHED,
        "license": None,
        "source_type": "secondary",
    }


@pytest.fixture
def client(monkeypatch):
    rows = [
        source_row(
            "https://www.pap.pl/aktualnosci/depesza-o-strajku?utm_source=x", "Strajk generalny we Włoszech 20 listopada"
        ),
        source_row("https://www.pap.pl/aktualnosci/inna-depesza", "Rząd przyjął projekt budżetu na 2027 rok"),
    ]

    async def fake_on_host(host, limit):
        return [row for row in rows if host in row["url"]]

    async def fake_between(start, end, limit):
        return [row for row in rows if row["published_at"] and start <= row["published_at"] <= end]

    monkeypatch.setattr(db, "sources_on_host", fake_on_host)
    monkeypatch.setattr(db, "sources_published_between", fake_between)
    app.state.incidents = FakeIncidents(
        [
            {
                "incident_id": "case-1",
                "source": "euvsdisinfo",
                "title": "Kampania o strajku",
                "url": "https://euvsdisinfo.eu/report/case-1",
                "published_at": "2026-11-21T00:00:00Z",
                "links": [normalize_url("https://m.example.org/post/1?fbclid=abc")],
            }
        ]
    )
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("HTTP://WWW.PAP.pl/aktualnosci/x/?utm_source=a&b=2&a=1#frag", "https://pap.pl/aktualnosci/x?a=1&b=2"),
        ("https://m.example.org/post/1?fbclid=abc", "https://example.org/post/1"),
        ("https://example.org", "https://example.org"),
    ],
)
def test_normalize_url(raw, expected):
    assert normalize_url(raw) == expected


def test_title_similarity_ignores_case_accents_and_short_words():
    assert material.title_similarity("Strajk generalny we Włoszech", "STRAJK GENERALNY WE WLOSZECH 20 listopada") == 1.0
    assert material.title_similarity("Strajk generalny we Włoszech", "Budżet na 2027 rok") == 0.0


def test_match_by_url_ignores_tracking_parameters_and_www(client):
    body = client.post("/match", json={"url": "https://pap.pl/aktualnosci/depesza-o-strajku"}).json()
    assert [item["basis"] for item in body["matches"]] == [["url"]]
    assert body["matches"][0]["kind"] == "corpus_document"
    assert body["matches"][0]["title"] == "Strajk generalny we Włoszech 20 listopada"


def test_match_by_title_and_date_requires_both(client):
    with_date = client.post(
        "/match",
        json={
            "url": "https://inny-portal.pl/kopia",
            "title": "Strajk generalny we Włoszech",
            "publishedAt": "2026-11-21T08:00:00Z",
        },
    ).json()
    assert [item["basis"] for item in with_date["matches"]] == [["title", "date"]]

    without_date = client.post(
        "/match", json={"url": "https://inny-portal.pl/kopia", "title": "Strajk generalny we Włoszech"}
    ).json()
    assert without_date["matches"] == []

    other_day = client.post(
        "/match",
        json={
            "url": "https://inny-portal.pl/kopia",
            "title": "Strajk generalny we Włoszech",
            "publishedAt": "2026-11-25T08:00:00Z",
        },
    ).json()
    assert other_day["matches"] == []


def test_domain_alone_is_not_a_match(client):
    body = client.post("/match", json={"url": "https://pap.pl/aktualnosci/zupelnie-inna-depesza"}).json()
    assert body["matches"] == []


def test_match_incident_link(client):
    body = client.post("/match", json={"url": "https://www.example.org/post/1/?fbclid=zzz"}).json()
    assert len(body["matches"]) == 1
    assert body["matches"][0]["kind"] == "incident"
    assert body["matches"][0]["incidentId"] == "case-1"
    assert body["matches"][0]["basis"] == ["url"]
