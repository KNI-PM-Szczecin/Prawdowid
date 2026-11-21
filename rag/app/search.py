import asyncio
import logging
import math
import time

from app import db
from app.config import settings
from app.context import build_context_xml, contains_instructions
from app.embeddings import EmbeddingModels
from app.models import Passage, SearchRequest, SearchResponse
from app.query_expansion import expand
from app.vector_store import RetrievedChunk, VectorStore

logger = logging.getLogger(__name__)

MILLISECONDS_PER_SECOND = 1000
INJECTION_FLAG = "suspected_injection"


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


async def search_passages(request: SearchRequest, models: EmbeddingModels, store: VectorStore) -> SearchResponse:
    """
    Full retrieval pipeline: query expansion -> parallel hybrid search -> cross-encoder rerank -> metadata join.

    Returns at most rerank_top_k_max passages above rerank_min_score; an empty list means no relevant evidence.
    Read counters are not updated here, the caller schedules db.register_reads for the returned chunks.
    """
    started_at = time.perf_counter()
    top_k = min(request.top_k or settings.rerank_top_k, settings.rerank_top_k_max)
    filters = request.filters

    queries = await expand(request.query)
    query_texts = [queries.original, queries.negative, queries.neutral]
    dense_vectors, sparse_vectors = await asyncio.to_thread(models.embed_queries, query_texts)
    result_sets = await asyncio.gather(
        *(
            store.hybrid_search(dense, sparse, settings.retrieval_limit_per_query)
            for dense, sparse in zip(dense_vectors, sparse_vectors)
        )
    )
    candidates = _merge_candidates(list(result_sets), settings.candidate_pool_size)

    passages: list[Passage] = []
    if candidates:
        logits = await asyncio.to_thread(models.rerank, queries.original, [chunk.text for chunk in candidates])
        scored = [(chunk, _relevance(logit)) for chunk, logit in zip(candidates, logits)]
        ranked = sorted(
            (pair for pair in scored if pair[1] >= settings.rerank_min_score),
            key=lambda pair: pair[1],
            reverse=True,
        )
        metadata = await db.fetch_passage_metadata(
            [chunk.chunk_id for chunk, _ in ranked],
            filters.source_types if filters else None,
            filters.published_after if filters else None,
        )
        for chunk, score in ranked:
            row = metadata.get(chunk.chunk_id)
            if row is None:
                continue
            flags = []
            if contains_instructions(chunk.text):
                flags.append(INJECTION_FLAG)
                logger.warning("Possible prompt injection in chunk %s (document %s)", chunk.chunk_id, row["document_id"])
            passages.append(
                Passage(
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
                    flags=flags,
                    chunk_id=chunk.chunk_id,
                    tier=row["tier"],
                    reliability=row["reliability"],
                )
            )
            if len(passages) == top_k:
                break

    elapsed_ms = round((time.perf_counter() - started_at) * MILLISECONDS_PER_SECOND)
    logger.info(
        "search done in %d ms: expansion=%s candidates=%d results=%d",
        elapsed_ms, queries.method, len(candidates), len(passages),
    )
    return SearchResponse(
        results=passages,
        corpus_version=await db.corpus_version(),
        context_xml=build_context_xml(passages),
        expanded_queries=queries,
        elapsed_ms=elapsed_ms,
    )
