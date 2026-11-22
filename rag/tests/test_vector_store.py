import asyncio

from app.vector_store import VectorStore


class StubResponse:
    def __init__(self):
        self.points = []


class StubClient:
    """Records the batch request; returns an empty response per request, like the real batch endpoint."""

    def __init__(self):
        self.requests = []

    async def query_batch_points(self, collection_name, requests):
        self.collection_name = collection_name
        self.requests = list(requests)
        return [StubResponse() for _ in self.requests]


def test_near_duplicate_document_queries_in_one_batch():
    store = VectorStore()
    stub = StubClient()
    store._client = stub

    result = asyncio.run(store.near_duplicate_document([[0.1, 0.2], [0.3, 0.4]], "doc-1"))

    assert result is None
    assert stub.collection_name == store._collection
    assert len(stub.requests) == 2
    for request in stub.requests:
        assert request.limit == 1
        assert request.using == "dense"
        assert request.filter.must_not[0].match.value == "doc-1"


def test_near_duplicate_document_without_vectors_skips_the_query():
    store = VectorStore()
    stub = StubClient()
    store._client = stub

    assert asyncio.run(store.near_duplicate_document([], "doc-1")) is None
    assert stub.requests == []
