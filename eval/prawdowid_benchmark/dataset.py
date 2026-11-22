import hashlib
import json
import random
import re
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

Gold = Literal["confirmed", "false", "misleading", "not_verifiable"]
Origin = Literal["google_factcheck", "manual"]

FACTCHECK_URL = "https://factchecktools.googleapis.com/v1alpha1/claims:search"
LANGUAGE = "pl"
PAGE_SIZE = 50
MAX_PAGES_PER_TOPIC = 4
REQUEST_TIMEOUT_SECONDS = 30.0
MIN_CLAIM_CHARS = 20
MAX_CLAIM_CHARS = 500
ID_PREFIX = "fc-"
ID_LENGTH = 10
DATASET_VERSION = 1

# Share of each gold class in the stratified set; a class short of claims leaves its slots to the others.
TARGET_SHARES: dict[str, float] = {"false": 0.4, "misleading": 0.3, "confirmed": 0.2, "not_verifiable": 0.1}
MAX_PER_TOPIC = 12
MAX_REVIEWER_SHARE = 0.6

# Order matters: "częściowa prawda" and "zbitka prawdy i fałszu" must land on misleading before "prawda" or
# "fałsz" match. Patterns are compared after normalisation (no diacritics, lower case).
RATING_RULES: tuple[tuple[Gold, tuple[str, ...]], ...] = (
    (
        "misleading",
        ("manipulac", "czesciow", "polprawd", "brak kontekstu", "wprowadza", "nieaktualn", "zbitka", "przekrecon"),
    ),
    ("not_verifiable", ("nieweryfikowaln", "niesprawdzaln", "opinia", "nie do sprawdzenia")),
    ("false", ("falsz", "nieprawd", "fake")),
    ("confirmed", ("prawda",)),
)
WHITESPACE = re.compile(r"\s+")


class BenchmarkModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class BenchmarkClaim(BenchmarkModel):
    id: str
    claim_text: str = Field(min_length=1)
    claimant: str | None = None
    claim_date: str | None = None
    gold: Gold
    gold_rating: str
    reviewer: str
    review_url: str
    review_title: str | None = None
    review_date: str | None = None
    topic: str
    origin: Origin = "google_factcheck"
    reviewed: bool = False
    note: str | None = None


class Dataset(BenchmarkModel):
    version: int = DATASET_VERSION
    built_at: str
    language: str = LANGUAGE
    size: int
    seed: int
    target_shares: dict[str, float]
    api_queries: list[str]
    claims: list[BenchmarkClaim]


class RejectedClaim(BenchmarkModel):
    claim_text: str
    reviewer: str | None
    rating: str | None
    reason: str


def normalize(text: str) -> str:
    """Lower case, no diacritics, single spaces: the key for rating rules and duplicate detection."""
    decomposed = unicodedata.normalize("NFKD", text.replace("ł", "l").replace("Ł", "L"))
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return WHITESPACE.sub(" ", without_marks).strip().casefold()


def map_rating(rating: str) -> Gold | None:
    """Fact-checker rating text to a gold label; anything the rules do not cover is None (rejected, never guessed)."""
    normalized = normalize(rating)
    for gold, needles in RATING_RULES:
        if any(needle in normalized for needle in needles):
            return gold
    return None


def claim_id(text: str) -> str:
    return ID_PREFIX + hashlib.sha1(normalize(text).encode("utf-8")).hexdigest()[:ID_LENGTH]


def _newest_review(reviews: list[dict]) -> dict | None:
    polish = [review for review in reviews if review.get("languageCode", LANGUAGE) == LANGUAGE]
    if not polish:
        return None
    return max(polish, key=lambda review: review.get("reviewDate") or "")


def parse_claims(payload: dict, topic: str) -> tuple[list[BenchmarkClaim], list[RejectedClaim]]:
    """Turns one API page into claims with gold labels; rejected entries keep the reason for the audit file."""
    accepted: list[BenchmarkClaim] = []
    rejected: list[RejectedClaim] = []
    for item in payload.get("claims", []):
        text = WHITESPACE.sub(" ", item.get("text") or "").strip()
        review = _newest_review(item.get("claimReview", []))
        reviewer = (review or {}).get("publisher", {}).get("name")
        rating = (review or {}).get("textualRating")
        if review is None or not review.get("url") or not rating:
            rejected.append(
                RejectedClaim(claim_text=text, reviewer=reviewer, rating=rating, reason="brak oceny lub linku")
            )
            continue
        if not MIN_CLAIM_CHARS <= len(text) <= MAX_CLAIM_CHARS:
            rejected.append(RejectedClaim(claim_text=text, reviewer=reviewer, rating=rating, reason="długość tekstu"))
            continue
        gold = map_rating(rating)
        if gold is None:
            rejected.append(
                RejectedClaim(claim_text=text, reviewer=reviewer, rating=rating, reason="ocena bez mapowania")
            )
            continue
        accepted.append(
            BenchmarkClaim(
                id=claim_id(text),
                claim_text=text,
                claimant=item.get("claimant"),
                claim_date=item.get("claimDate"),
                gold=gold,
                gold_rating=rating.strip(),
                reviewer=reviewer or "nieznany",
                review_url=review["url"],
                review_title=review.get("title"),
                review_date=review.get("reviewDate"),
                topic=topic,
            )
        )
    return accepted, rejected


def fetch_topic(client: httpx.Client, api_key: str, topic: str) -> list[dict]:
    """All pages for one topic query, up to MAX_PAGES_PER_TOPIC; the key travels in a header, never in the URL."""
    pages: list[dict] = []
    page_token: str | None = None
    for _ in range(MAX_PAGES_PER_TOPIC):
        params = {"query": topic, "languageCode": LANGUAGE, "pageSize": PAGE_SIZE}
        if page_token:
            params["pageToken"] = page_token
        response = client.get(FACTCHECK_URL, params=params, headers={"X-Goog-Api-Key": api_key})
        response.raise_for_status()
        payload = response.json()
        pages.append(payload)
        page_token = payload.get("nextPageToken")
        if not page_token:
            break
    return pages


def dedupe(claims: list[BenchmarkClaim]) -> list[BenchmarkClaim]:
    """One entry per claim text (the newest review wins); the same claim often comes back under several topics."""
    newest: dict[str, BenchmarkClaim] = {}
    for claim in claims:
        current = newest.get(claim.id)
        if current is None or (claim.review_date or "") > (current.review_date or ""):
            newest[claim.id] = claim
    return list(newest.values())


def stratify(claims: list[BenchmarkClaim], size: int, seed: int) -> list[BenchmarkClaim]:
    """
    Picks `size` claims close to TARGET_SHARES, at most MAX_PER_TOPIC per topic and MAX_REVIEWER_SHARE from one
    reviewer. Deterministic for a seed. Slots a class cannot fill go to the other classes in share order.
    """
    pools: dict[str, list[BenchmarkClaim]] = {gold: [] for gold in TARGET_SHARES}
    for claim in claims:
        pools[claim.gold].append(claim)
    shuffler = random.Random(seed)
    for pool in pools.values():
        pool.sort(key=lambda claim: claim.id)
        shuffler.shuffle(pool)

    selected: list[BenchmarkClaim] = []
    chosen_ids: set[str] = set()
    per_topic: dict[str, int] = {}
    per_reviewer: dict[str, int] = {}
    max_per_reviewer = max(1, int(size * MAX_REVIEWER_SHARE))

    def take(gold: str, wanted: int, cap_reviewer: bool) -> int:
        taken = 0
        for claim in pools[gold]:
            if taken == wanted:
                break
            if claim.id in chosen_ids or per_topic.get(claim.topic, 0) >= MAX_PER_TOPIC:
                continue
            if cap_reviewer and per_reviewer.get(claim.reviewer, 0) >= max_per_reviewer:
                continue
            selected.append(claim)
            chosen_ids.add(claim.id)
            per_topic[claim.topic] = per_topic.get(claim.topic, 0) + 1
            per_reviewer[claim.reviewer] = per_reviewer.get(claim.reviewer, 0) + 1
            taken += 1
        return taken

    # Target shares with both caps; then the same shares without the reviewer cap (one reviewer may dominate
    # Polish fact-checking); finally any class fills what is left.
    for cap_reviewer in (True, False):
        for gold, share in TARGET_SHARES.items():
            already = sum(1 for claim in selected if claim.gold == gold)
            take(gold, round(size * share) - already, cap_reviewer)
    for gold in TARGET_SHARES:
        if len(selected) >= size:
            break
        take(gold, size - len(selected), cap_reviewer=False)
    return sorted(selected, key=lambda claim: claim.id)


def build_dataset(
    api_key: str,
    topics: list[str],
    size: int,
    seed: int,
    transport: httpx.BaseTransport | None = None,
    now: datetime | None = None,
) -> tuple[Dataset, list[RejectedClaim]]:
    accepted: list[BenchmarkClaim] = []
    rejected: list[RejectedClaim] = []
    with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS, transport=transport) as client:
        for topic in topics:
            for page in fetch_topic(client, api_key, topic):
                page_accepted, page_rejected = parse_claims(page, topic)
                accepted.extend(page_accepted)
                rejected.extend(page_rejected)
    unique = dedupe(accepted)
    selected = stratify(unique, size, seed)
    dataset = Dataset(
        built_at=(now or datetime.now(UTC)).isoformat(timespec="seconds"),
        size=len(selected),
        seed=seed,
        target_shares=TARGET_SHARES,
        api_queries=topics,
        claims=selected,
    )
    return dataset, rejected


def load_dataset(path: Path) -> Dataset:
    dataset = Dataset.model_validate(json.loads(path.read_text(encoding="utf-8")))
    ids = [claim.id for claim in dataset.claims]
    duplicates = sorted({claim_id for claim_id in ids if ids.count(claim_id) > 1})
    if duplicates:
        raise ValueError(f"Duplicate claim ids: {duplicates}")
    return dataset


def save_json(path: Path, model: BaseModel | list[BaseModel]) -> None:
    payload = (
        [item.model_dump(by_alias=True) for item in model]
        if isinstance(model, list)
        else model.model_dump(by_alias=True)
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_topics(path: Path) -> list[str]:
    return json.loads(path.read_text(encoding="utf-8"))["topics"]
