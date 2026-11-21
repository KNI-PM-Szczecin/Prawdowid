import asyncio
import logging
import time

from app import db
from app.config import settings
from app.context import build_context_xml, contains_instructions
from app.embeddings import EmbeddingModels
from app.models import Evidence, SearchResponse, SourceOut
from app.query_expansion import expand
from app.vector_store import RetrievedChunk, VectorStore

logger = logging.getLogger(__name__)

MILLISECONDS_PER_SECOND = 1000


def _merge_candidates(result_sets: list[list[RetrievedChunk]], pool_size: int) -> list[RetrievedChunk]:
    best_by_id: dict = {}
    for results in result_sets:
        for chunk in results:
            current = best_by_id.get(chunk.chunk_id)
            if current is None or chunk.fusion_score > current.fusion_score:
                best_by_id[chunk.chunk_id] = chunk
    return sorted(best_by_id.values(), key=lambda chunk: chunk.fusion_score, reverse=True)[:pool_size]


async def search_evidence(
    claim: str, requested_top_k: int | None, models: EmbeddingModels, store: VectorStore
) -> SearchResponse:
    """
    Full retrieval pipeline: query expansion -> parallel hybrid search -> cross-encoder rerank -> metadata join.

    Returns at most rerank_top_k_max evidence chunks; an empty list means the corpus has nothing on the claim.
    Read counters are not updated here, the caller schedules db.register_reads for the returned ids.
    """
    started_at = time.perf_counter()
    top_k = min(requested_top_k or settings.rerank_top_k, settings.rerank_top_k_max)

    queries = await expand(claim)
    query_texts = [queries.original, queries.negative, queries.neutral]
    dense_vectors, sparse_vectors = await asyncio.to_thread(models.embed_queries, query_texts)
    result_sets = await asyncio.gather(
        *(
            store.hybrid_search(dense, sparse, settings.retrieval_limit_per_query)
            for dense, sparse in zip(dense_vectors, sparse_vectors)
        )
    )
    candidates = _merge_candidates(list(result_sets), settings.candidate_pool_size)

    evidence: list[Evidence] = []
    if candidates:
        scores = await asyncio.to_thread(models.rerank, queries.original, [chunk.text for chunk in candidates])
        ranked = sorted(
            (pair for pair in zip(candidates, scores) if pair[1] >= settings.rerank_min_score),
            key=lambda pair: pair[1],
            reverse=True,
        )
        metadata = await db.fetch_evidence_metadata([chunk.chunk_id for chunk, _ in ranked])
        for chunk, score in ranked:
            row = metadata.get(chunk.chunk_id)
            if row is None:
                continue
            suspicious = contains_instructions(chunk.text)
            if suspicious:
                logger.warning("Possible prompt injection in chunk %s (source %s)", chunk.chunk_id, row["source_id"])
            evidence.append(
                Evidence(
                    chunk_id=chunk.chunk_id,
                    text=chunk.text,
                    rerank_score=score,
                    tier=row["tier"],
                    reliability=row["reliability"],
                    topic_tag=row["topic_tag"],
                    source=SourceOut(**{field: row[field] for field in SourceOut.model_fields}),
                    suspicious_instructions=suspicious,
                )
            )
            if len(evidence) == top_k:
                break

    elapsed_ms = round((time.perf_counter() - started_at) * MILLISECONDS_PER_SECOND)
    logger.info(
        "search done in %d ms: expansion=%s candidates=%d evidence=%d",
        elapsed_ms, queries.method, len(candidates), len(evidence),
    )
    return SearchResponse(
        queries=queries, evidence=evidence, context_xml=build_context_xml(evidence), elapsed_ms=elapsed_ms
    )
