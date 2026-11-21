import asyncio
import logging
import time

from app.config import settings
from app.embeddings import EmbeddingModels
from app.vector_store import VectorStore

logger = logging.getLogger(__name__)

MILLISECONDS_PER_SECOND = 1000
# Same shape as the first real request: three expanded queries, one hybrid search each, a full rerank pool.
# The text is deliberately unrelated to the corpus, so the warm-up never influences later answers.
WARMUP_QUERIES = (
    "rozgrzewka modeli wyszukiwania",
    "rozgrzewka modeli wyszukiwania zaprzeczenie",
    "rozgrzewka modeli wyszukiwania neutralne",
)
WARMUP_DOCUMENT = "Fragment rozgrzewkowy. Nie pochodzi z korpusu i nie jest zapisywany."


async def warm_up(models: EmbeddingModels, store: VectorStore) -> None:
    """
    Runs the retrieval pipeline once during startup: ONNX sessions, the reranker and the Qdrant connection are the
    expensive part of the first search, and Railway routes traffic as soon as the process reports readiness.
    A failure is logged and does not block startup; the service still answers, only the first request is slower.
    """
    started_at = time.perf_counter()
    try:
        dense_vectors, sparse_vectors = await asyncio.to_thread(models.embed_queries, list(WARMUP_QUERIES))
        for dense, sparse in zip(dense_vectors, sparse_vectors, strict=True):
            await store.hybrid_search(dense, sparse, 1, None)
        await asyncio.to_thread(models.rerank, WARMUP_QUERIES[0], [WARMUP_DOCUMENT] * settings.candidate_pool_size)
    except Exception:
        logger.exception("Warm-up failed; the first search will pay the model loading cost")
        return
    elapsed_ms = round((time.perf_counter() - started_at) * MILLISECONDS_PER_SECOND)
    logger.info("Warm-up finished in %d ms", elapsed_ms)
