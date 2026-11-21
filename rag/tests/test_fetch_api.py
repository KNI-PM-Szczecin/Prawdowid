import pytest
from fastapi.testclient import TestClient

from app import main
from app.config import settings
from app.fetcher import FetchedPage, FetchError
from app.main import app


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


def test_fetch_returns_page_text_and_truncation_flag(client, monkeypatch):
    monkeypatch.setattr(settings, "fetch_max_text_chars", 20)

    async def fake_fetch_page(http_client, url):
        return FetchedPage(
            url=url, title="Komunikat", text="Treść strony, która jest dłuższa niż limit.", published_at=None
        )

    monkeypatch.setattr(main, "fetch_page", fake_fetch_page)
    body = client.post("/fetch", json={"url": "https://www.gov.pl/web/rcb/x"}).json()
    assert body["title"] == "Komunikat"
    assert body["text"] == "Treść strony, która je"[:20]
    assert body["truncated"] is True


def test_fetch_failure_is_422_with_reason(client, monkeypatch):
    async def failing_fetch_page(http_client, url):
        raise FetchError("HTTP 403")

    monkeypatch.setattr(main, "fetch_page", failing_fetch_page)
    response = client.post("/fetch", json={"url": "https://ulc.gov.pl/x"})
    assert response.status_code == 422
    assert "HTTP 403" in response.json()["detail"]


def test_fetch_rejects_non_url(client):
    assert client.post("/fetch", json={"url": "not a url"}).status_code == 422
