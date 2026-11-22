import asyncio
from uuid import UUID

from app.embeddings import SparseVector
from app.reports import match_report
from app.vector_store import RawPoint, RetrievedChunk

HIGH_LOGIT = 8.0
LOW_LOGIT = -6.0

LIMANOWA = "Od przyszłego miesiąca w Limanowej parkowanie w centrum będzie możliwe wyłącznie przez aplikację."
LIMANOWA_PARAPHRASE = "W Limanowej od przyszłego miesiąca można parkować w centrum tylko przez aplikację."
LIMANOWA_PRICE = "W Limanowej podrożeje parkowanie w centrum."
PCIM = "Od wczoraj w Pcimiu bilety autobusowe można kupić tylko przez aplikację."


class FakeModels:
    def __init__(self, similar: set[tuple[str, str]]):
        self._similar = similar

    def embed_queries(self, texts):
        return [[0.0]] * len(texts), [SparseVector(indices=[], values=[])] * len(texts)

    embed_documents = embed_queries

    def rerank(self, query, documents):
        return [HIGH_LOGIT if (query, document) in self._similar else LOW_LOGIT for document in documents]


class MemoryStore:
    def __init__(self):
        self.points: list[RawPoint] = []

    async def hybrid_search(self, dense, sparse, limit, payload_filter):
        return [
            RetrievedChunk(chunk_id=point.point_id, text=point.payload["text"], fusion_score=0.5, payload=point.payload)
            for point in self.points[:limit]
        ]

    async def upsert_raw(self, points):
        self.points.extend(points)


def both_ways(first: str, second: str) -> set[tuple[str, str]]:
    return {(first, second), (second, first)}


def test_first_report_opens_a_case_and_is_stored():
    store = MemoryStore()
    case_id, matched, score = asyncio.run(match_report(LIMANOWA, FakeModels(set()), store))
    assert isinstance(case_id, UUID) and not matched and score is None
    assert [point.payload["case_id"] for point in store.points] == [str(case_id)]


def test_paraphrase_joins_the_same_case():
    store, models = MemoryStore(), FakeModels(both_ways(LIMANOWA, LIMANOWA_PARAPHRASE))
    first, _, _ = asyncio.run(match_report(LIMANOWA, models, store))
    second, matched, score = asyncio.run(match_report(LIMANOWA_PARAPHRASE, models, store))
    assert matched and second == first and score > 0.65
    assert len(store.points) == 2


def test_similarity_in_one_direction_only_opens_a_new_case():
    store, models = MemoryStore(), FakeModels({(LIMANOWA_PRICE, LIMANOWA)})
    first, _, _ = asyncio.run(match_report(LIMANOWA, models, store))
    second, matched, _ = asyncio.run(match_report(LIMANOWA_PRICE, models, store))
    assert not matched and second != first


def test_other_topic_opens_a_new_case():
    store, models = MemoryStore(), FakeModels(both_ways(LIMANOWA, LIMANOWA_PARAPHRASE))
    first, _, _ = asyncio.run(match_report(LIMANOWA, models, store))
    second, matched, _ = asyncio.run(match_report(PCIM, models, store))
    assert not matched and second != first


def test_third_report_can_match_any_earlier_report_of_the_case():
    third = "Parkowanie w centrum Limanowej będzie tylko przez aplikację."
    store, models = (
        MemoryStore(),
        FakeModels(both_ways(LIMANOWA, LIMANOWA_PARAPHRASE) | both_ways(LIMANOWA_PARAPHRASE, third)),
    )
    first, _, _ = asyncio.run(match_report(LIMANOWA, models, store))
    asyncio.run(match_report(LIMANOWA_PARAPHRASE, models, store))
    case_id, matched, _ = asyncio.run(match_report(third, models, store))
    assert matched and case_id == first
