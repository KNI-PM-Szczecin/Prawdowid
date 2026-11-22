import asyncio

import httpx
import pytest

from app.config import settings
from app.factcheck import API_KEY_HEADER, FactCheckClient, matches_claim, parse_reviews, query_variants

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
    first = asyncio.run(client.search("Czy Polska wystąpi z Unii?"))
    second = asyncio.run(client.search("Czy Polska wystąpi z Unii?"))

    assert first.status == second.status == "ok"
    assert len(first.reviews) == 1
    assert sorted(request.url.params["query"] for request in requests) == [
        "Czy Polska wystąpi z Unii?",
        "Polska wystąpi Unii",
    ]
    assert all(request.headers[API_KEY_HEADER] == API_KEY for request in requests)
    assert all(API_KEY not in str(request.url) for request in requests)
    assert all(request.url.params["languageCode"] == "pl" for request in requests)


def test_query_variants_add_expanded_focused_and_core_phrasings_once():
    assert query_variants("Zielonogródek wydaje na kolej około 900 mln zł.", "Zielonogródek kolej wydatki") == [
        "Zielonogródek wydaje na kolej około 900 mln zł.",
        "Zielonogródek wydaje kolej około 900 mln",
        "Zielonogródek kolej wydatki",
        "Zielonogródek kolej 900 mln",
        "Zielonogródek kolej",
    ]
    assert query_variants("polexit") == ["polexit"]


def test_focused_phrasings_drop_verbs_and_use_base_forms():
    assert query_variants("Agencja ZPA usunęła depeszę o wypowiedzi polityka.")[2:] == [
        "Agencja ZPA wypowiedzi polityka",
        "Agencja ZPA depesza",
    ]


def test_review_with_other_figures_does_not_match_a_claim_with_numbers():
    claim = "Zielonogródek wydaje na kolej około 900 mln zł."
    same_topic = parse_reviews(
        _review_payload("Zielonogródek wydaje na kolej mniej niż Borowo.", "https://w.example/a"), 1
    )
    same_figure = parse_reviews(
        _review_payload("Kolej kosztuje Zielonogródek ok. 900 mln zł.", "https://w.example/b"), 1
    )
    assert not matches_claim(claim, same_topic[0])
    assert matches_claim(claim, same_figure[0])


def test_query_variants_capped_at_max_attempts(monkeypatch):
    monkeypatch.setattr(settings, "factcheck_max_attempts", 2)
    assert len(query_variants("Czy w fikcyjnym mieście Zielonogródku otwarto nowy most kolejowy?")) == 2


def _review_payload(claim_text: str, url: str) -> dict:
    return {
        "claims": [
            {
                "text": claim_text,
                "claimReview": [
                    {"publisher": {"name": "Weryfikator A"}, "url": url, "textualRating": "Fałsz"},
                ],
            }
        ]
    }


MATCHING = _review_payload("W Zielonogródku otwarto nowy most kolejowy.", "https://weryfikator-a.example/most")
UNRELATED = _review_payload("Szczepionki zawierają mikroczipy.", "https://weryfikator-a.example/czipy")
CLAIM = "Czy w Zielonogródku otwarto nowy most kolejowy nad rzeką?"


def test_retries_shorter_phrasings_until_a_matching_review(monkeypatch):
    monkeypatch.setattr(settings, "factcheck_api_key", API_KEY)
    variants = query_variants(CLAIM)
    matching_from = variants[3]
    queries = []

    def handler(request: httpx.Request) -> httpx.Response:
        query = request.url.params["query"]
        queries.append(query)
        if query == matching_from:
            return httpx.Response(200, json=MATCHING)
        return httpx.Response(200, json=UNRELATED if query == variants[0] else {})

    result = asyncio.run(_client(handler).search(CLAIM))

    assert result.status == "ok"
    assert result.reviews[0].url == "https://weryfikator-a.example/most"
    assert len(queries) == 4
    assert queries[-1] == matching_from


def test_no_retries_when_first_wave_matches(monkeypatch):
    monkeypatch.setattr(settings, "factcheck_api_key", API_KEY)
    queries = []

    def handler(request: httpx.Request) -> httpx.Response:
        queries.append(request.url.params["query"])
        return httpx.Response(200, json=MATCHING)

    asyncio.run(_client(handler).search(CLAIM))
    assert len(queries) == 2


def test_stops_after_max_attempts_when_nothing_matches(monkeypatch):
    monkeypatch.setattr(settings, "factcheck_api_key", API_KEY)
    queries = []

    def handler(request: httpx.Request) -> httpx.Response:
        queries.append(request.url.params["query"])
        return httpx.Response(200, json=UNRELATED)

    result = asyncio.run(_client(handler).search(CLAIM, "Zielonogródek most rzeka"))
    assert result.status == "ok"
    assert sorted(queries) == sorted(query_variants(CLAIM, "Zielonogródek most rzeka"))
    assert len(queries) <= settings.factcheck_max_attempts
    assert [review.url for review in result.reviews] == ["https://weryfikator-a.example/czipy"]


def test_failed_retry_stops_retrying(monkeypatch):
    monkeypatch.setattr(settings, "factcheck_api_key", API_KEY)
    variants = query_variants(CLAIM)
    queries = []

    def handler(request: httpx.Request) -> httpx.Response:
        query = request.url.params["query"]
        queries.append(query)
        if query == variants[2]:
            return httpx.Response(429, json={"error": "quota"})
        return httpx.Response(200, json={})

    result = asyncio.run(_client(handler).search(CLAIM))
    assert result.status == "ok"
    assert len(queries) == 3


def test_one_failing_variant_still_returns_results(monkeypatch):
    monkeypatch.setattr(settings, "factcheck_api_key", API_KEY)

    def handler(request: httpx.Request) -> httpx.Response:
        if "?" in request.url.params["query"]:
            return httpx.Response(503)
        return httpx.Response(200, json=PAYLOAD)

    result = asyncio.run(_client(handler).search("Czy Polska wystąpi z Unii?"))
    assert result.status == "ok"
    assert len(result.reviews) == 1


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
