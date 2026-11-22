import json
from datetime import UTC, datetime

import httpx

from prawdowid_benchmark.dataset import (
    MAX_PER_TOPIC,
    BenchmarkClaim,
    build_dataset,
    claim_id,
    dedupe,
    map_rating,
    parse_claims,
    stratify,
)


def _review(rating: str, url: str = "https://demagog.org.pl/x", date: str = "2026-10-01T00:00:00Z") -> dict:
    return {
        "publisher": {"name": "Demagog"},
        "url": url,
        "textualRating": rating,
        "reviewDate": date,
        "languageCode": "pl",
    }


def _api_claim(text: str, rating: str, **review) -> dict:
    return {
        "text": text,
        "claimant": "Użytkownik Facebooka",
        "claimDate": "2026-09-01T00:00:00Z",
        "claimReview": [_review(rating, **review)],
    }


def test_rating_mapping_puts_partial_truth_before_truth_and_rejects_unknown():
    assert map_rating("Fałsz") == "false"
    assert map_rating("fałsz") == "false"
    assert map_rating("Prawda") == "confirmed"
    assert map_rating("Częściowa prawda") == "misleading"
    assert map_rating("Zbitka prawdy i fałszu") == "misleading"
    assert map_rating("Manipulacja") == "misleading"
    assert map_rating("Nieweryfikowalne") == "not_verifiable"
    assert map_rating("Niemożliwe do oceny") is None
    assert map_rating("3/10") is None


def test_parse_claims_keeps_provenance_and_rejects_with_reason():
    payload = {
        "claims": [
            _api_claim("Szczepionki powodują autyzm.", "Fałsz"),
            _api_claim("Krótkie.", "Fałsz"),
            _api_claim("Twierdzenie z oceną, której nie mapujemy do żadnej klasy.", "Niemożliwe do oceny"),
            {"text": "Bez weryfikacji, za to odpowiednio długie zdanie.", "claimReview": []},
        ]
    }
    accepted, rejected = parse_claims(payload, "szczepionki")
    assert [claim.gold for claim in accepted] == ["false"]
    assert accepted[0].reviewer == "Demagog" and accepted[0].topic == "szczepionki"
    assert accepted[0].id == claim_id("szczepionki powodują AUTYZM.")
    assert [item.reason for item in rejected] == ["długość tekstu", "ocena bez mapowania", "brak oceny lub linku"]


def test_dedupe_keeps_the_newest_review_of_the_same_text():
    old = parse_claims(
        {"claims": [_api_claim("To samo twierdzenie o czymś.", "Fałsz", date="2025-01-01T00:00:00Z")]}, "a"
    )[0][0]
    new = parse_claims(
        {"claims": [_api_claim("To samo  twierdzenie o czymś.", "Prawda", date="2026-01-01T00:00:00Z")]}, "b"
    )[0][0]
    assert old.id == new.id
    assert [claim.gold for claim in dedupe([old, new])] == ["confirmed"]


def _claim(index: int, gold: str, topic: str = "t", reviewer: str = "Demagog") -> BenchmarkClaim:
    return BenchmarkClaim(
        id=f"fc-{index:010d}",
        claim_text=f"Twierdzenie numer {index} o czymś ważnym.",
        gold=gold,
        gold_rating=gold,
        reviewer=reviewer,
        review_url=f"https://example.org/{index}",
        topic=topic,
    )


def test_stratify_follows_target_shares_and_caps_per_topic():
    claims = [_claim(index, "false", topic=f"t{index % 3}") for index in range(60)]
    claims += [_claim(100 + index, "misleading", topic=f"m{index % 5}") for index in range(60)]
    claims += [_claim(200 + index, "confirmed", topic=f"c{index % 5}") for index in range(60)]
    claims += [_claim(300 + index, "not_verifiable", topic=f"n{index % 5}") for index in range(60)]
    selected = stratify(claims, size=50, seed=1)
    by_gold = {
        gold: sum(1 for claim in selected if claim.gold == gold)
        for gold in ("false", "misleading", "confirmed", "not_verifiable")
    }
    # false has only 3 topics x MAX_PER_TOPIC available, so its 20 slots cannot all be filled.
    assert by_gold["false"] == min(20, 3 * MAX_PER_TOPIC)
    assert by_gold["misleading"] >= 15 and by_gold["confirmed"] >= 10 and by_gold["not_verifiable"] >= 5
    assert len(selected) == 50
    assert selected == stratify(claims, size=50, seed=1)
    assert selected != stratify(claims, size=50, seed=2)


def test_build_dataset_pages_through_the_api_and_sends_key_in_header():
    seen_headers = []
    seen_tokens = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers.append(request.headers.get("X-Goog-Api-Key"))
        seen_tokens.append(request.url.params.get("pageToken"))
        assert "key" not in request.url.params
        if request.url.params.get("pageToken") == "p2":
            return httpx.Response(200, json={"claims": [_api_claim("Druga strona twierdzeń o Ukrainie.", "Prawda")]})
        return httpx.Response(
            200,
            json={"claims": [_api_claim("Pierwsza strona twierdzeń o Ukrainie.", "Fałsz")], "nextPageToken": "p2"},
        )

    dataset, rejected = build_dataset(
        "secret",
        ["Ukraina"],
        size=10,
        seed=1,
        transport=httpx.MockTransport(handler),
        now=datetime(2026, 11, 22, tzinfo=UTC),
    )
    assert seen_headers == ["secret", "secret"] and seen_tokens == [None, "p2"]
    assert sorted(claim.gold for claim in dataset.claims) == ["confirmed", "false"]
    assert dataset.api_queries == ["Ukraina"] and rejected == []
    assert json.loads(dataset.model_dump_json(by_alias=True))["claims"][0]["reviewUrl"]
