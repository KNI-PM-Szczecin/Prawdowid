import asyncio

from app import warmup
from app.embeddings import SparseVector


class WarmFakeModels:
    def __init__(self, failure: Exception | None = None) -> None:
        self.embed_calls = 0
        self.rerank_calls = 0
        self._failure = failure

    def embed_queries(self, queries):
        self.embed_calls = len(queries)
        if self._failure is not None:
            raise self._failure
        return [[0.0]] * len(queries), [SparseVector(indices=[], values=[])] * len(queries)

    def rerank(self, query, documents):
        self.rerank_calls = len(documents)
        return [0.0] * len(documents)


class WarmFakeStore:
    def __init__(self, failure: Exception | None = None) -> None:
        self.searches = 0
        self._failure = failure

    async def hybrid_search(self, dense, sparse, limit, payload_filter):
        if self._failure is not None:
            raise self._failure
        self.searches += 1
        return []


def test_warm_up_touches_every_model_and_qdrant():
    models = WarmFakeModels()
    store = WarmFakeStore()

    asyncio.run(warmup.warm_up(models, store))

    assert models.embed_calls == len(warmup.WARMUP_QUERIES)
    assert store.searches == len(warmup.WARMUP_QUERIES)
    assert models.rerank_calls == warmup.settings.candidate_pool_size


def test_warm_up_failure_does_not_stop_startup():
    models = WarmFakeModels(failure=RuntimeError("model file missing"))

    asyncio.run(warmup.warm_up(models, WarmFakeStore()))

    assert models.rerank_calls == 0


def test_warm_up_survives_qdrant_failure():
    models = WarmFakeModels()

    asyncio.run(warmup.warm_up(models, WarmFakeStore(failure=RuntimeError("qdrant down"))))

    assert models.rerank_calls == 0
