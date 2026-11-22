import asyncio
import hashlib
import json
import logging
import math
import time
from collections import Counter
from datetime import UTC, datetime
from uuid import UUID

from app import db
from app.caching import TtlCache
from app.config import settings
from app.context import build_context_xml, contains_instructions
from app.embeddings import EmbeddingModels
from app.factcheck import FACTCHECK_RELIABILITY, FACTCHECK_TIER, FactCheckClient, FactCheckResult, FactCheckReview
from app.incidents import CATALOG_STATUS_NAME, build_campaign_alert
from app.incidents import rerank_text as incident_rerank_text
from app.models import ExternalSourceStatus, Passage, SearchFilters, SearchRequest, SearchResponse
from app.query_expansion import expand
from app.vector_store import RetrievedChunk, VectorStore, build_filter

logger = logging.getLogger(__name__)

MILLISECONDS_PER_SECOND = 1000
INJECTION_FLAG = "suspected_injection"

_cache: TtlCache[str, tuple[str, SearchResponse]] = TtlCache(
    settings.search_cache_ttl_seconds, settings.search_cache_max_entries
)


def _cache_key(request: SearchRequest) -> str:
    return hashlib.sha256(json.dumps(request.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()


def _cached(key: str, corpus_version: str) -> SearchResponse | None:
    entry = _cache.get(key)
    if entry is None or entry[0] != corpus_version:
        return None
    return entry[1]


def _remember(key: str, corpus_version: str, response: SearchResponse) -> None:
    _cache.put(key, (corpus_version, response))


FACTCHECK_SOURCE_TYPE = "factcheck"
FACTCHECK_DOCUMENT_PREFIX = "factcheck:"

Candidate = RetrievedChunk | FactCheckReview


def _relevance(logit: float) -> float:
    """Maps the cross-encoder logit to the 0..1 score required by CONTRACT.md."""
    return 1.0 / (1.0 + math.exp(-logit / settings.rerank_score_temperature))


def _merge_candidates(result_sets: list[list[RetrievedChunk]], pool_size: int) -> list[RetrievedChunk]:
    best_by_id: dict[UUID, RetrievedChunk] = {}
    for results in result_sets:
        for chunk in results:
            current = best_by_id.get(chunk.chunk_id)
            if current is None or chunk.fusion_score > current.fusion_score:
                best_by_id[chunk.chunk_id] = chunk
    return sorted(best_by_id.values(), key=lambda chunk: chunk.fusion_score, reverse=True)[:pool_size]


def _diversify(chunks: list[RetrievedChunk], max_per_document: int) -> list[RetrievedChunk]:
    """Caps chunks per document, so one long page cannot fill the rerank pool and starve independent
    evidence from other publishers (brief: verdict strength comes from independent confirmations)."""
    selected: list[RetrievedChunk] = []
    per_document: Counter[str] = Counter()
    for chunk in chunks:  # already sorted by fusion score
        document = chunk.payload.get("source_id") or str(chunk.chunk_id)
        if per_document[document] >= max_per_document:
            continue
        per_document[document] += 1
        selected.append(chunk)
    return selected[: settings.candidate_pool_size]


def _factcheck_wanted(filters: SearchFilters | None) -> bool:
    return filters is None or not filters.source_types or FACTCHECK_SOURCE_TYPE in filters.source_types


def _within_date_filter(review: FactCheckReview, filters: SearchFilters | None) -> bool:
    if filters is None or filters.published_after is None:
        return True
    return review.review_date is not None and review.review_date > filters.published_after


def _published_key(candidate: Candidate) -> str:
    """Publication date as a comparable ISO string; a missing date sorts oldest. Recency only breaks
    score ties — it never overrides the cross-encoder (brief: prefer current material, no domain shortcuts)."""
    if isinstance(candidate, FactCheckReview):
        return candidate.review_date.isoformat() if candidate.review_date else ""
    return candidate.payload.get("published_at") or ""


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


def _complete_corpus_metadata(row) -> bool:
    """Citations always carry title, publisher, publication date, fetch date and link (AGENTS.md §4, brief §5)."""
    return all(row[field] for field in ("title", "publisher", "url", "published_at", "fetched_at"))


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
    request: SearchRequest,
    models: EmbeddingModels,
    store: VectorStore,
    factcheck: FactCheckClient,
    incidents: VectorStore,
) -> SearchResponse:
    """
    Full retrieval pipeline: query expansion -> parallel hybrid search in the corpus, the incident catalog and
    live Google Fact Check -> one cross-encoder rerank over all candidates -> metadata join.

    Returns at most request.top_k passages above rerank_min_score; an empty list means no relevant evidence.
    Incident catalog matches never enter `results` or `context_xml`: they only build `campaign_alert` (context).
    A failing or disabled fact-check source never fails the search, it is reported in external_sources.
    Read counters are not updated here, the caller schedules db.register_reads for the returned corpus chunks.
    """
    started_at = time.perf_counter()
    corpus_version = await db.corpus_version()
    cache_key = _cache_key(request)
    cached = _cached(cache_key, corpus_version)
    if cached is not None:
        elapsed_ms = round((time.perf_counter() - started_at) * MILLISECONDS_PER_SECOND)
        logger.info("search served from cache in %d ms", elapsed_ms)
        return cached.model_copy(update={"elapsed_ms": elapsed_ms})
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
    *result_sets, incident_hits, catalog_size = await asyncio.gather(
        *(
            store.hybrid_search(dense, sparse, settings.retrieval_limit_per_query, payload_filter)
            for dense, sparse in zip(dense_vectors, sparse_vectors, strict=True)
        ),
        incidents.hybrid_search(dense_vectors[0], sparse_vectors[0], settings.incident_retrieval_limit, None),
        incidents.count(),
    )
    factcheck_result = await factcheck_task
    reviews = [review for review in factcheck_result.reviews if _within_date_filter(review, filters)]
    candidates: list[Candidate] = [
        *_diversify(
            _merge_candidates(list(result_sets), settings.retrieval_limit_per_query),
            settings.pool_max_chunks_per_document,
        ),
        *reviews,
    ]

    corpus_candidates = [candidate for candidate in candidates if isinstance(candidate, RetrievedChunk)]
    metadata_task = asyncio.create_task(db.fetch_passage_metadata([chunk.chunk_id for chunk in corpus_candidates]))

    passages: list[Passage] = []
    campaign_alert = None
    if candidates or incident_hits:
        rerank_texts = [
            *(
                candidate.rerank_text if isinstance(candidate, FactCheckReview) else candidate.text
                for candidate in candidates
            ),
            *(incident_rerank_text(hit) for hit in incident_hits),
        ]
        logits = await asyncio.to_thread(models.rerank, queries.original, rerank_texts)
        relevances = [_relevance(logit) for logit in logits]
        scored = list(zip(candidates, relevances[: len(candidates)], strict=True))
        campaign_alert = build_campaign_alert(list(zip(incident_hits, relevances[len(candidates) :], strict=True)))
        ranked = sorted(
            sorted(
                (pair for pair in scored if pair[1] >= settings.rerank_min_score),
                key=lambda pair: _published_key(pair[0]),
                reverse=True,
            ),
            # Stable sort: equal scores keep the recency order of the inner sort.
            key=lambda pair: pair[1],
            reverse=True,
        )
        fetched_at = datetime.now(UTC)
        metadata = await metadata_task
        skipped_incomplete = 0
        for candidate, score in ranked:
            if isinstance(candidate, FactCheckReview):
                if candidate.review_date is None:
                    skipped_incomplete += 1
                    continue
                passages.append(_factcheck_passage(candidate, score, fetched_at))
            elif (row := metadata.get(candidate.chunk_id)) is not None:
                if not _complete_corpus_metadata(row):
                    skipped_incomplete += 1
                    continue
                passages.append(_corpus_passage(candidate, row, score))
            if len(passages) == request.top_k:
                break
        if skipped_incomplete:
            logger.info("Dropped %d passages without complete metadata", skipped_incomplete)
    else:
        await metadata_task

    elapsed_ms = round((time.perf_counter() - started_at) * MILLISECONDS_PER_SECOND)
    logger.info(
        "search done in %d ms: expansion=%s candidates=%d results=%d factcheck=%s/%d campaign_matches=%d",
        elapsed_ms,
        queries.method,
        len(candidates),
        len(passages),
        factcheck_result.status,
        len(reviews),
        len(campaign_alert.matches) if campaign_alert else 0,
    )
    catalog_status = ExternalSourceStatus(
        name=CATALOG_STATUS_NAME,
        status="ok" if catalog_size else "disabled",
        results=len(campaign_alert.matches) if campaign_alert else 0,
    )
    response = SearchResponse(
        results=passages,
        corpus_version=corpus_version,
        context_xml=build_context_xml(passages),
        expanded_queries=queries,
        elapsed_ms=elapsed_ms,
        external_sources=[factcheck_result.as_status(), catalog_status],
        campaign_alert=campaign_alert,
    )
    _remember(cache_key, corpus_version, response)
    return response
