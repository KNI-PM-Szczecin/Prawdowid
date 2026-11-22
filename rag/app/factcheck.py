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


def query_variants(query: str) -> list[str]:
    """The claim as given plus its keywords (corpus-language stopwords removed), without duplicates."""
    stopwords = load_profile(settings.corpus_language).stopwords
    keywords: list[str] = []
    seen: set[str] = set()
    for word in WORD.findall(query):
        folded = word.casefold()
        if folded not in stopwords and folded not in seen:
            seen.add(folded)
            keywords.append(word)
    keyword_query = " ".join(keywords[:FACTCHECK_MAX_KEYWORDS])
    variants = [query.strip()]
    if keyword_query and keyword_query.casefold() != variants[0].casefold():
        variants.append(keyword_query)
    return variants


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

    async def search(self, query: str) -> FactCheckResult:
        """
        Sends the full claim and its keyword form in parallel: Google matches short keyword queries far better
        (measured on Polish claims), while the full claim keeps exact phrasings. Results are merged by review URL.
        """
        if not self.enabled:
            return FactCheckResult(status="disabled", reviews=[])
        outcomes = await asyncio.gather(*(self._search_one(variant) for variant in query_variants(query)))
        successful = [reviews for reviews in outcomes if reviews is not None]
        if not successful:
            return FactCheckResult(status="error", reviews=[])
        merged: dict[UUID, FactCheckReview] = {}
        for reviews in successful:
            for review in reviews:
                merged.setdefault(review.review_id, review)
        return FactCheckResult(status="ok", reviews=list(merged.values())[: settings.factcheck_max_reviews])

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
