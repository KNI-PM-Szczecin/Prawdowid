import hashlib
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from uuid import NAMESPACE_URL, UUID, uuid5

import httpx

from app.config import settings
from app.models import ExternalSourceStatus

logger = logging.getLogger(__name__)

SOURCE_NAME = "google_factcheck"
API_KEY_HEADER = "X-Goog-Api-Key"
# Google indexes ClaimReview markup from any publisher, not only IFCN signatories: trusted tier, medium reliability.
FACTCHECK_TIER = 2
FACTCHECK_RELIABILITY = "medium"


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


class FactCheckClient:
    """Live Google Fact Check Tools claims:search; never raises, failures become an explicit `error` status."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._client = httpx.AsyncClient(timeout=settings.factcheck_timeout_seconds, transport=transport)
        self._cache: dict[str, tuple[float, list[FactCheckReview]]] = {}

    @property
    def enabled(self) -> bool:
        return bool(settings.factcheck_api_key)

    @staticmethod
    def _cache_key(query: str) -> str:
        """Hash, not the claim itself, so user text is not kept in memory longer than the request."""
        return hashlib.sha256(query.encode("utf-8")).hexdigest()

    def _cached(self, query: str) -> list[FactCheckReview] | None:
        entry = self._cache.get(self._cache_key(query))
        if entry is None or entry[0] < time.monotonic():
            return None
        return entry[1]

    def _remember(self, query: str, reviews: list[FactCheckReview]) -> None:
        if len(self._cache) >= settings.factcheck_cache_max_entries:
            self._cache.pop(next(iter(self._cache)))
        self._cache[self._cache_key(query)] = (time.monotonic() + settings.factcheck_cache_ttl_seconds, reviews)

    async def search(self, query: str) -> FactCheckResult:
        if not self.enabled:
            return FactCheckResult(status="disabled", reviews=[])
        cached = self._cached(query)
        if cached is not None:
            return FactCheckResult(status="ok", reviews=cached)
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
            return FactCheckResult(status="error", reviews=[])
        except (httpx.HTTPError, ValueError) as error:
            logger.warning("Google Fact Check search failed: %s", type(error).__name__)
            return FactCheckResult(status="error", reviews=[])
        self._remember(query, reviews)
        return FactCheckResult(status="ok", reviews=reviews)

    async def close(self) -> None:
        await self._client.aclose()
