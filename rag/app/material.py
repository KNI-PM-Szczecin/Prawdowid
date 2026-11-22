import re
import unicodedata
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from app import db
from app.incidents import LINKS_FIELD
from app.models import MaterialMatchBasis, MaterialMatchItem, MaterialMatchRequest, MaterialMatchResponse
from app.urls import normalize_url
from app.vector_store import VectorStore

# Brief scenario I: the same material is recognised by its address, or by title and publication date together.
# A similar topic or the domain alone never counts as the same material.
TITLE_MIN_SIMILARITY = 0.6
DATE_TOLERANCE = timedelta(days=1)
CANDIDATES_LIMIT = 300
MAX_MATCHES = 5
TOKEN_PATTERN = re.compile(r"[^\W_]+")
SHORT_TOKEN_MAX_CHARS = 2
# NFKD leaves the stroke of "ł" alone, so it is mapped by hand (as in app/context.py).
POLISH_LETTERS_WITHOUT_DECOMPOSITION = str.maketrans({"ł": "l"})


def title_tokens(title: str) -> set[str]:
    folded = unicodedata.normalize("NFKD", title.casefold().translate(POLISH_LETTERS_WITHOUT_DECOMPOSITION))
    without_marks = "".join(character for character in folded if not unicodedata.combining(character))
    return {token for token in TOKEN_PATTERN.findall(without_marks) if len(token) > SHORT_TOKEN_MAX_CHARS}


def title_similarity(first: str, second: str) -> float:
    """Jaccard overlap of title words; one title fully contained in the other counts as identical."""
    tokens_first, tokens_second = title_tokens(first), title_tokens(second)
    if not tokens_first or not tokens_second:
        return 0.0
    if tokens_first <= tokens_second or tokens_second <= tokens_first:
        return 1.0
    return len(tokens_first & tokens_second) / len(tokens_first | tokens_second)


def same_day(first: datetime | None, second: datetime | None) -> bool:
    return first is not None and second is not None and abs(first - second) <= DATE_TOLERANCE


def _corpus_item(row, basis: list[MaterialMatchBasis]) -> MaterialMatchItem:
    return MaterialMatchItem(
        kind="corpus_document",
        basis=basis,
        title=row["title"],
        publisher=row["publisher"],
        url=row["url"],
        published_at=row["published_at"],
        source_type=row["source_type"],
    )


async def match_material(request: MaterialMatchRequest, incidents: VectorStore) -> MaterialMatchResponse:
    """
    Finds the submitted page in the corpus (by address, or by title plus publication date) and in the incident
    catalog (by the addresses of the material that spread the campaign). The result is context about the
    material, never about the truth of its content.
    """
    wanted = normalize_url(str(request.url))
    host = urlsplit(wanted).hostname or ""
    matches: list[MaterialMatchItem] = []
    seen_urls: set[str] = set()

    for row in await db.sources_on_host(host, CANDIDATES_LIMIT):
        if normalize_url(row["url"]) == wanted:
            matches.append(_corpus_item(row, ["url"]))
            seen_urls.add(wanted)

    title = (request.title or "").strip()
    if title and request.published_at is not None:
        candidates = await db.sources_published_between(
            request.published_at - DATE_TOLERANCE, request.published_at + DATE_TOLERANCE, CANDIDATES_LIMIT
        )
        for row in candidates:
            candidate_url = normalize_url(row["url"])
            if candidate_url in seen_urls:
                continue
            if title_similarity(title, row["title"]) >= TITLE_MIN_SIMILARITY:
                matches.append(_corpus_item(row, ["title", "date"]))
                seen_urls.add(candidate_url)

    for payload in await incidents.find_by_payload(LINKS_FIELD, wanted, MAX_MATCHES):
        matches.append(
            MaterialMatchItem(
                kind="incident",
                basis=["url"],
                title=payload["title"],
                publisher=payload["source"],
                url=payload["url"],
                published_at=payload.get("published_at"),
                incident_id=payload["incident_id"],
                source=payload["source"],
            )
        )
    return MaterialMatchResponse(matches=matches[:MAX_MATCHES])
