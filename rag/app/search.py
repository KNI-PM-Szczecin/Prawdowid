import asyncio
import logging
import math
import time
from datetime import UTC, datetime

from app import db
from app.config import settings
from app.context import build_context_xml, contains_instructions
from app.embeddings import EmbeddingModels
from app.factcheck import FACTCHECK_RELIABILITY, FACTCHECK_TIER, FactCheckClient, FactCheckResult, FactCheckReview
from app.models import Passage, SearchFilters, SearchRequest, SearchResponse
from app.query_expansion import expand
from app.vector_store import RetrievedChunk, VectorStore, build_filter

logger = logging.getLogger(__name__)

MILLISECONDS_PER_SECOND = 1000
INJECTION_FLAG = "suspected_injection"
FACTCHECK_SOURCE_TYPE = "factcheck"
FACTCHECK_DOCUMENT_PREFIX = "factcheck:"

Candidate = RetrievedChunk | FactCheckReview


def _relevance(logit: float) -> float:
    """Maps the cross-encoder logit to the 0..1 score required by CONTRACT.md."""
    return 1.0 / (1.0 + math.exp(-logit / settings.rerank_score_temperature))


def _merge_candidates(result_sets: list[list[RetrievedChunk]], pool_size: int) -> list[RetrievedChunk]:
    best_by_id: dict = {}
    for results in result_sets:
        for chunk in results:
            current = best_by_id.get(chunk.chunk_id)
            if current is None or chunk.fusion_score > current.fusion_score:
                best_by_id[chunk.chunk_id] = chunk
    return sorted(best_by_id.values(), key=lambda chunk: chunk.fusion_score, reverse=True)[:pool_size]


def _factcheck_wanted(filters: SearchFilters | None) -> bool:
    return filters is None or not filters.source_types or FACTCHECK_SOURCE_TYPE in filters.source_types


def _within_date_filter(review: FactCheckReview, filters: SearchFilters | None) -> bool:
    if filters is None or filters.published_after is None:
        return True
    return review.review_date is not None and review.review_date > filters.published_after


def _flags(text: str, label: str) -> list[str]:
    if not contains_instructions(text):
        return []
    logger.warning("Possible prompt injection in %s", label)
    return [INJECTION_FLAG]


def _factcheck_passage(review: FactCheckReview, score: float, fetched_at: datetime) -> Passage:
    text = review.passage_text
    return Passage(
        document_id=f"{FACTCHECK_DOCUMENT_PREFIX}{review.review_id}",
        title=review.title or review.claim_text,
        publisher=review.publisher,
        published_at=review.review_date,
        fetched_at=fetched_at,
        url=review.url,
        license=None,
        source_type=FACTCHECK_SOURCE_TYPE,
        passage=text,
        score=score,
        flags=_flags(text, f"fact-check review {review.url}"),
        chunk_id=review.review_id,
        tier=FACTCHECK_TIER,
        reliability=FACTCHECK_RELIABILITY,
    )


def _corpus_passage(chunk: RetrievedChunk, row, score: float) -> Passage:
    return Passage(
        document_id=row["document_id"],
        title=row["title"],
        publisher=row["publisher"],
        published_at=row["published_at"],
        fetched_at=row["fetched_at"],
        url=row["url"],
        license=row["license"],
        source_type=row["source_type"],
        passage=chunk.text,
        score=score,
        flags=_flags(chunk.text, f"chunk {chunk.chunk_id} (document {row['document_id']})"),
        chunk_id=chunk.chunk_id,
        tier=row["tier"],
        reliability=row["reliability"],
    )


async def _skipped_factcheck() -> FactCheckResult:
    return FactCheckResult(status="skipped", reviews=[])


async def search_passages(
    request: SearchRequest, models: EmbeddingModels, store: VectorStore, factcheck: FactCheckClient
) -> SearchResponse:
    """
    Full retrieval pipeline: query expansion -> parallel hybrid search in the corpus and live Google Fact Check
    -> one cross-encoder rerank over both -> metadata join.

    Returns at most request.top_k passages above rerank_min_score; an empty list means no relevant evidence.
    A failing or disabled fact-check source never fails the search, it is reported in external_sources.
    Read counters are not updated here, the caller schedules db.register_reads for the returned corpus chunks.
    """
    started_at = time.perf_counter()
    filters = request.filters
    payload_filter = build_filter(
        filters.source_types if filters else None, filters.published_after if filters else None
    )
    factcheck_task = asyncio.create_task(
        factcheck.search(request.query) if _factcheck_wanted(filters) else _skipped_factcheck()
    )

    queries = await expand(request.query)
    query_texts = [queries.original, queries.negative, queries.neutral]
    dense_vectors, sparse_vectors = await asyncio.to_thread(models.embed_queries, query_texts)
    result_sets = await asyncio.gather(
        *(
            store.hybrid_search(dense, sparse, settings.retrieval_limit_per_query, payload_filter)
            for dense, sparse in zip(dense_vectors, sparse_vectors, strict=True)
        )
    )
    factcheck_result = await factcheck_task
    reviews = [review for review in factcheck_result.reviews if _within_date_filter(review, filters)]
    candidates: list[Candidate] = [*_merge_candidates(list(result_sets), settings.candidate_pool_size), *reviews]

    passages: list[Passage] = []
    if candidates:
        rerank_texts = [
            candidate.rerank_text if isinstance(candidate, FactCheckReview) else candidate.text
            for candidate in candidates
        ]
        logits = await asyncio.to_thread(models.rerank, queries.original, rerank_texts)
        scored = [(candidate, _relevance(logit)) for candidate, logit in zip(candidates, logits, strict=True)]
        ranked = sorted(
            (pair for pair in scored if pair[1] >= settings.rerank_min_score),
            key=lambda pair: pair[1],
            reverse=True,
        )
        metadata = await db.fetch_passage_metadata(
            [candidate.chunk_id for candidate, _ in ranked if isinstance(candidate, RetrievedChunk)]
        )
        fetched_at = datetime.now(UTC)
        for candidate, score in ranked:
            if isinstance(candidate, FactCheckReview):
                passages.append(_factcheck_passage(candidate, score, fetched_at))
            elif (row := metadata.get(candidate.chunk_id)) is not None:
                passages.append(_corpus_passage(candidate, row, score))
            if len(passages) == request.top_k:
                break

    elapsed_ms = round((time.perf_counter() - started_at) * MILLISECONDS_PER_SECOND)
    logger.info(
        "search done in %d ms: expansion=%s candidates=%d results=%d factcheck=%s/%d",
        elapsed_ms,
        queries.method,
        len(candidates),
        len(passages),
        factcheck_result.status,
        len(reviews),
    )
    return SearchResponse(
        results=passages,
        corpus_version=await db.corpus_version(),
        context_xml=build_context_xml(passages),
        expanded_queries=queries,
        elapsed_ms=elapsed_ms,
        external_sources=[factcheck_result.as_status()],
    )
