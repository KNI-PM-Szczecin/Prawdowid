import asyncio
from uuid import uuid4

import pytest
from qdrant_client import AsyncQdrantClient

from app import db, instance
from app.config import settings
from app.vector_store import VectorStore


def _memory_store() -> VectorStore:
    store = VectorStore("instance_test")
    store._client = AsyncQdrantClient(location=":memory:")
    return store


def test_qdrant_identity_is_created_once_and_kept():
    async def scenario():
        store = _memory_store()
        await store.ensure_collection()
        return await store.instance_id(), await store.instance_id()

    first, second = asyncio.run(scenario())
    assert first == second


class FakeStore:
    def __init__(self, identity):
        self.identity = identity

    async def instance_id(self):
        return self.identity


def _owned_by(monkeypatch, owner):
    calls = []

    async def claim_database(instance_id, take_over):
        calls.append(take_over)
        return instance_id if owner is None or take_over else owner

    monkeypatch.setattr(db, "claim_database", claim_database)
    return calls


def test_first_qdrant_claims_a_free_database(monkeypatch):
    _owned_by(monkeypatch, None)
    asyncio.run(instance.ensure_database_owner(FakeStore(uuid4())))


def test_second_qdrant_on_the_same_database_refuses_to_start(monkeypatch):
    _owned_by(monkeypatch, uuid4())
    with pytest.raises(instance.ForeignDatabaseError, match="RAG_CLAIM_DATABASE"):
        asyncio.run(instance.ensure_database_owner(FakeStore(uuid4())))


def test_explicit_claim_takes_the_database_over(monkeypatch):
    calls = _owned_by(monkeypatch, uuid4())
    monkeypatch.setattr(settings, "claim_database", True)
    asyncio.run(instance.ensure_database_owner(FakeStore(uuid4())))
    assert calls == [True]
