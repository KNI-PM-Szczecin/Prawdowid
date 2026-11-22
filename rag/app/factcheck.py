import asyncio
import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from uuid import NAMESPACE_URL, UUID, uuid5

import httpx

from app.caching import TtlCache
from app.config import settings
from app.languages import load_profile
from app.models import ExternalSourceStatus

logger = logging.getLogger(__name__)

SOURCE_NAME = "google_factcheck"
API_KEY_HEADER = "X-Goog-Api-Key"
# Google indexes ClaimReview markup from any publisher, not only IFCN signatories: trusted tier, medium reliability.
FACTCHECK_TIER = 2
FACTCHECK_RELIABILITY = "medium"
# Google's claim search matched short keyword queries best in tests on Polish claims.
FACTCHECK_MAX_KEYWORDS = 6
# Google matches base forms: "Wrocław komunikacja 700 mln" finds a review that "Wrocław wydaje na komunikację"
# misses. The focused phrasing keeps names, numbers and nouns, the core phrasing a name and one noun.
FACTCHECK_FOCUSED_WORDS = 4
FACTCHECK_CORE_NAMES = 2
# Verb forms add nothing to a claim search and often break it ("usunęła", "wydaje", "kosztują").
VERB_ENDINGS = ("ł", "ła", "ło", "li", "ły", "uje", "ują", "aje", "ają")
# Feminine accusative to nominative, the most common inflection in claims ("depeszę" -> "depesza").
ACCUSATIVE_ENDING, NOMINATIVE_ENDING = "ę", "a"
MIN_INFLECTED_WORD_LENGTH = 5
# Words that belong to the number before them ("700 mln", "6,2 proc").
UNIT_WORDS = frozenset({"mln", "mld", "tys", "proc", "zł", "euro", "km"})
# Variants sent together in the first wave; the rest are tried one by one only when nothing matched.
FACTCHECK_FIRST_WAVE_SIZE = 2
# Polish inflects nouns ("Wrocław", "Wrocławiu"), so words are compared by their first letters.
MATCH_STEM_LENGTH = 5
MATCH_MIN_WORD_LENGTH = 4
MATCH_MIN_SHARED_STEMS = 2
WORD = re.compile(r"\w+", re.UNICODE)


@dataclass(frozen=True)
class FactCheckReview:
    review_id: UUID
    claim_text: str
    claimant: str | None
    publisher: str
    url: str
    title: str | None
    rating: str
    review_date: datetime | None

    @property
    def rerank_text(self) -> str:
        return f"{self.claim_text} {self.title or ''}".strip()

    @property
    def passage_text(self) -> str:
        """Polish summary shown as the passage; the rating is the fact-checker's, not ours."""
        claimant = f" (autor twierdzenia: {self.claimant})" if self.claimant else ""
        title = f" Tytuł weryfikacji: {self.title}." if self.title else ""
        return (
            f"Twierdzenie sprawdzone przez weryfikatora faktów: {self.claim_text}{claimant}. "
            f"Ocena weryfikatora ({self.publisher}): {self.rating}.{title}"
        )


@dataclass(frozen=True)
class FactCheckResult:
    status: str
    reviews: list[FactCheckReview]

    def as_status(self) -> ExternalSourceStatus:
        return ExternalSourceStatus(name=SOURCE_NAME, status=self.status, results=len(self.reviews))


def _parse_timestamp(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        logger.warning("Unparseable fact-check timestamp %r", raw)
        return None


def parse_reviews(payload: dict, max_reviews: int) -> list[FactCheckReview]:
    """Flattens claims[].claimReview[] into reviews; entries without a URL or rating cannot be cited and are dropped."""
    reviews: list[FactCheckReview] = []
    for claim in payload.get("claims", []):
        claim_text = (claim.get("text") or "").strip()
        if not claim_text:
            continue
        for review in claim.get("claimReview", []):
            url = review.get("url")
            rating = (review.get("textualRating") or "").strip()
            publisher = review.get("publisher") or {}
            publisher_name = publisher.get("name") or publisher.get("site")
            if not url or not rating or not publisher_name:
                continue
            reviews.append(
                FactCheckReview(
                    review_id=uuid5(NAMESPACE_URL, url),
                    claim_text=claim_text,
                    claimant=claim.get("claimant"),
                    publisher=publisher_name,
                    url=url,
                    title=review.get("title"),
                    rating=rating,
                    review_date=_parse_timestamp(review.get("reviewDate")),
                )
            )
            if len(reviews) == max_reviews:
                return reviews
    return reviews


def _keywords(text: str) -> list[str]:
    stopwords = load_profile(settings.corpus_language).stopwords
    keywords: list[str] = []
    seen: set[str] = set()
    for word in WORD.findall(text):
        folded = word.casefold()
        if folded not in stopwords and folded not in seen:
            seen.add(folded)
            keywords.append(word)
    return keywords


def _is_number(word: str) -> bool:
    return any(character.isdigit() for character in word)


def _is_name(word: str) -> bool:
    return word[0].isupper() and not _is_number(word)


def _base_form(word: str) -> str:
    if len(word) >= MIN_INFLECTED_WORD_LENGTH and word.endswith(ACCUSATIVE_ENDING):
        return word[: -len(ACCUSATIVE_ENDING)] + NOMINATIVE_ENDING
    return word


def _focused_phrasings(keywords: list[str]) -> tuple[str, str]:
    """
    The focused phrasing (names, the longest noun, numbers with their units, then other nouns, at most
    FACTCHECK_FOCUSED_WORDS, in claim order) and the core phrasing (up to FACTCHECK_CORE_NAMES names plus the first
    noun).
    """
    words = [
        _base_form(word)
        for word in keywords
        if _is_name(word) or _is_number(word) or not word.casefold().endswith(VERB_ENDINGS)
    ]
    names = [word for word in words if _is_name(word)]
    numbers = [word for word in words if _is_number(word) or word.casefold() in UNIT_WORDS]
    nouns = [word for word in words if word not in names and word not in numbers]
    longest_nouns = sorted(nouns, key=len, reverse=True)
    chosen = set((names + longest_nouns[:1] + numbers + longest_nouns[1:])[:FACTCHECK_FOCUSED_WORDS])
    focused = " ".join(word for word in words if word in chosen)
    core = " ".join(names[:FACTCHECK_CORE_NAMES] + nouns[:1])
    return focused, core


def query_variants(query: str, expanded_keywords: str | None = None) -> list[str]:
    """
    Phrasings of the claim in the order they are tried, without duplicates and at most
    settings.factcheck_max_attempts: the claim as given, its keywords, the keywords from query expansion (nominative
    nouns when a model expands queries), then the focused and the core phrasing built without a model.
    """
    keywords = _keywords(query)
    focused, core = _focused_phrasings(keywords)
    candidates = [
        query.strip(),
        " ".join(keywords[:FACTCHECK_MAX_KEYWORDS]),
        (expanded_keywords or "").strip(),
        focused,
        core,
    ]
    variants: list[str] = []
    seen: set[frozenset[str]] = set()
    for candidate in candidates:
        words = frozenset(word.casefold() for word in WORD.findall(candidate))
        if words and words not in seen:
            seen.add(words)
            variants.append(candidate)
    return variants[: settings.factcheck_max_attempts]


def _stems(text: str) -> set[str]:
    return {word.casefold()[:MATCH_STEM_LENGTH] for word in _keywords(text) if len(word) >= MATCH_MIN_WORD_LENGTH}


def matches_claim(query: str, review: FactCheckReview) -> bool:
    """
    True when the reviewed claim or its title shares enough topic words with the user's claim and, when the claim
    has numbers, at least one of them: a review on the same topic with other figures is a different claim.
    """
    claim_stems = _stems(query)
    if not claim_stems:
        return False
    review_text = review.rerank_text
    claim_numbers = {word for word in WORD.findall(query) if word.isdigit()}
    if claim_numbers and not claim_numbers & set(WORD.findall(review_text)):
        return False
    shared = claim_stems & _stems(review_text)
    return len(shared) >= min(MATCH_MIN_SHARED_STEMS, len(claim_stems))


class FactCheckClient:
    """Live Google Fact Check Tools claims:search; never raises, failures become an explicit `error` status."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._client = httpx.AsyncClient(timeout=settings.factcheck_timeout_seconds, transport=transport)
        self._cache: TtlCache[str, list[FactCheckReview]] = TtlCache(
            settings.factcheck_cache_ttl_seconds, settings.factcheck_cache_max_entries
        )

    @property
    def enabled(self) -> bool:
        return bool(settings.factcheck_api_key)

    @staticmethod
    def _cache_key(query: str) -> str:
        """Hash, not the claim itself, so user text is not kept in memory longer than the request."""
        return hashlib.sha256(query.encode("utf-8")).hexdigest()

    def _cached(self, query: str) -> list[FactCheckReview] | None:
        return self._cache.get(self._cache_key(query))

    def _remember(self, query: str, reviews: list[FactCheckReview]) -> None:
        self._cache.put(self._cache_key(query), reviews)

    async def search(self, query: str, expanded_keywords: str | None = None) -> FactCheckResult:
        """
        Sends the full claim and its keyword form in parallel: Google matches short keyword queries far better
        (measured on Polish claims), while the full claim keeps exact phrasings. Google's search is sensitive to
        wording, so when those find nothing that matches the claim, shorter phrasings are tried one by one
        (settings.factcheck_max_attempts in total, within settings.factcheck_retry_budget_seconds).
        A failed request is not retried: it means a key, quota or network problem, not a wording problem.
        Results are merged by review URL.
        """
        if not self.enabled:
            return FactCheckResult(status="disabled", reviews=[])
        variants = query_variants(query, expanded_keywords)
        first_wave, retries = variants[:FACTCHECK_FIRST_WAVE_SIZE], variants[FACTCHECK_FIRST_WAVE_SIZE:]
        outcomes = await asyncio.gather(*(self._search_one(variant) for variant in first_wave))
        successful = [reviews for reviews in outcomes if reviews is not None]
        if not successful:
            return FactCheckResult(status="error", reviews=[])
        merged: dict[UUID, FactCheckReview] = {}
        for reviews in successful:
            for review in reviews:
                merged.setdefault(review.review_id, review)
        if retries and not any(matches_claim(query, review) for review in merged.values()):
            await self._retry_phrasings(query, retries, merged)
        ordered = sorted(merged.values(), key=lambda review: not matches_claim(query, review))
        return FactCheckResult(status="ok", reviews=ordered[: settings.factcheck_max_reviews])

    async def _retry_phrasings(self, query: str, variants: list[str], merged: dict[UUID, FactCheckReview]) -> None:
        try:
            async with asyncio.timeout(settings.factcheck_retry_budget_seconds):
                for variant in variants:
                    reviews = await self._search_one(variant)
                    if reviews is None:
                        return
                    for review in reviews:
                        merged.setdefault(review.review_id, review)
                    if any(matches_claim(query, review) for review in reviews):
                        return
        except TimeoutError:
            logger.info(
                "Google Fact Check retries stopped at the %.1f s budget", settings.factcheck_retry_budget_seconds
            )

    async def _search_one(self, query: str) -> list[FactCheckReview] | None:
        cached = self._cached(query)
        if cached is not None:
            return cached
        try:
            response = await self._client.get(
                settings.factcheck_url,
                params={
                    "query": query,
                    "languageCode": settings.factcheck_language,
                    "pageSize": settings.factcheck_page_size,
                },
                headers={API_KEY_HEADER: settings.factcheck_api_key},
            )
            response.raise_for_status()
            reviews = parse_reviews(response.json(), settings.factcheck_max_reviews)
        except httpx.HTTPStatusError as error:
            # No exc_info: the request URL carries the user's claim, which must not land in logs.
            logger.warning("Google Fact Check search failed with HTTP %d", error.response.status_code)
            return None
        except (httpx.HTTPError, ValueError) as error:
            logger.warning("Google Fact Check search failed: %s", type(error).__name__)
            return None
        self._remember(query, reviews)
        return reviews

    async def close(self) -> None:
        await self._client.aclose()
