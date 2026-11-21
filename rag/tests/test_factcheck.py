import asyncio

import httpx
import pytest

from app.config import settings
from app.factcheck import API_KEY_HEADER, FactCheckClient, parse_reviews

API_KEY = "test-factcheck-key"
MAX_REVIEWS = 10

PAYLOAD = {
    "claims": [
        {
            "text": "Polska wystąpi z Unii Europejskiej w przyszłym roku.",
            "claimant": "Konto w mediach społecznościowych",
            "claimDate": "2026-10-01T00:00:00Z",
            "claimReview": [
                {
                    "publisher": {"name": "Weryfikator A", "site": "weryfikator-a.example"},
                    "url": "https://weryfikator-a.example/polexit",
                    "title": "Nie, Polska nie wychodzi z UE",
                    "reviewDate": "2026-10-03T00:00:00Z",
                    "textualRating": "Fałsz",
                    "languageCode": "pl",
                },
                {"publisher": {"name": "Bez linku"}, "textualRating": "Fałsz"},
            ],
        },
        {"text": "", "claimReview": [{"url": "https://x.example", "textualRating": "Prawda"}]},
    ]
}


def _client(handler) -> FactCheckClient:
    return FactCheckClient(transport=httpx.MockTransport(handler))


def test_parse_reviews_keeps_only_citable_reviews():
    reviews = parse_reviews(PAYLOAD, MAX_REVIEWS)
    assert len(reviews) == 1
    review = reviews[0]
    assert review.publisher == "Weryfikator A"
    assert review.rating == "Fałsz"
    assert review.review_date.year == 2026
    assert "Ocena weryfikatora (Weryfikator A): Fałsz." in review.passage_text


def test_disabled_without_key_and_makes_no_request(monkeypatch):
    monkeypatch.setattr(settings, "factcheck_api_key", "")

    def handler(request):
        raise AssertionError("no request expected")

    result = asyncio.run(_client(handler).search("twierdzenie"))
    assert (result.status, result.reviews) == ("disabled", [])


def test_sends_key_in_header_not_url_and_caches(monkeypatch):
    monkeypatch.setattr(settings, "factcheck_api_key", API_KEY)
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=PAYLOAD)

    client = _client(handler)
    first = asyncio.run(client.search("polexit"))
    second = asyncio.run(client.search("polexit"))

    assert first.status == second.status == "ok"
    assert len(first.reviews) == 1
    assert len(requests) == 1
    assert requests[0].headers[API_KEY_HEADER] == API_KEY
    assert API_KEY not in str(requests[0].url)
    assert requests[0].url.params["languageCode"] == "pl"


@pytest.mark.parametrize(
    "handler",
    [
        lambda request: httpx.Response(429, json={"error": "quota"}),
        lambda request: httpx.Response(200, text="not json"),
        lambda request: (_ for _ in ()).throw(httpx.ConnectTimeout("timeout", request=request)),
    ],
)
def test_failures_become_error_status(monkeypatch, handler):
    monkeypatch.setattr(settings, "factcheck_api_key", API_KEY)
    result = asyncio.run(_client(handler).search("twierdzenie"))
    assert (result.status, result.reviews) == ("error", [])
