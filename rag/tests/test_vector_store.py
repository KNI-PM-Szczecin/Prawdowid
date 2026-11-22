import asyncio
import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app import db
from app.config import settings
from app.vector_store import RawPoint, VectorStore, build_filter

pytestmark = pytest.mark.skipif(
    not os.environ.get("RAG_TEST_DSN"), reason="RAG_TEST_DSN (Postgres with pgvector) not set"
)

DIMENSION = settings.dense_dim
OLD = datetime(2020, 1, 1, tzinfo=UTC)
NEW = datetime(2026, 6, 1, tzinfo=UTC)


def axis(index: int, weight: float = 1.0, other: int | None = None) -> list[float]:
    """A unit-ish vector along one axis, optionally leaning towards a second one."""
    vector = [0.0] * DIMENSION
    vector[index] = weight
    if other is not None:
        vector[other] = 1.0 - weight
    return vector


def point(
    index: int, tokens: list[str], source_id: str, source_type: str = "official", published: datetime = NEW, **extra
):
    return RawPoint(
        point_id=uuid4(),
        dense=axis(index),
        lexical=tokens,
        payload={
            "text": f"tekst {index}",
            "source_id": source_id,
            "source_type": source_type,
            "published_at": published.isoformat(),
            **extra,
        },
    )


def run_with_store(scenario):
    """Runs scenario(store) against a throwaway table in the test database and drops the table afterwards."""

    async def runner():
        settings.postgres_dsn = os.environ["RAG_TEST_DSN"]
        await db.connect()
        store = VectorStore(f"test_{uuid4().hex}")
        try:
            await store.ensure_collection()
            return await scenario(store)
        finally:
            await db.pool().execute(f"DROP TABLE IF EXISTS {store._table}")
            await db.close()

    return asyncio.run(runner())


def test_hybrid_search_fuses_dense_and_lexical_candidates():
    async def scenario(store):
        dense_only = point(0, ["inne"], "doc-a")
        lexical_only = point(1, ["senat", "senator"], "doc-b")
        both = point(2, ["senat", "senator", "sto"], "doc-c")
        await store.upsert_raw([dense_only, lexical_only, both])
        hits = await store.hybrid_search(axis(2), ["senat", "senator", "sto"], 10, None)
        return [hit.chunk_id for hit in hits], both.point_id, {dense_only.point_id, lexical_only.point_id}

    ranked, both_id, others = run_with_store(scenario)
    assert ranked[0] == both_id
    assert others <= set(ranked)


def test_search_without_lexical_tokens_falls_back_to_dense_ranking():
    async def scenario(store):
        near, far = point(3, [], "doc-a"), point(4, [], "doc-b")
        await store.upsert_raw([far, near])
        hits = await store.hybrid_search(axis(3), [], 5, None)
        return [hit.chunk_id for hit in hits], near.point_id

    ranked, near_id = run_with_store(scenario)
    assert ranked[0] == near_id


def test_filters_apply_to_both_halves_of_the_search():
    async def scenario(store):
        official_old = point(5, ["konstytucja"], "doc-a", "official", OLD)
        secondary_new = point(5, ["konstytucja"], "doc-b", "secondary", NEW)
        await store.upsert_raw([official_old, secondary_new])
        by_type = await store.hybrid_search(axis(5), ["konstytucja"], 5, build_filter(["secondary"], None))
        by_date = await store.hybrid_search(
            axis(5), ["konstytucja"], 5, build_filter(None, datetime(2024, 1, 1, tzinfo=UTC))
        )
        return [h.chunk_id for h in by_type], [h.chunk_id for h in by_date], secondary_new.point_id

    by_type, by_date, expected = run_with_store(scenario)
    assert by_type == [expected]
    assert by_date == [expected]


def test_upsert_replaces_a_point_and_delete_removes_it():
    async def scenario(store):
        original = point(6, ["stary"], "doc-a")
        await store.upsert_raw([original])
        replaced = RawPoint(original.point_id, axis(6), ["nowy"], {**original.payload, "text": "nowy tekst"})
        await store.upsert_raw([replaced])
        hits = await store.hybrid_search(axis(6), ["nowy"], 5, None)
        count_before, ids = await store.count(), await store.point_ids()
        await store.delete([original.point_id])
        return hits[0].text, count_before, ids == [original.point_id], await store.count()

    text, count_before, ids_match, count_after = run_with_store(scenario)
    assert (text, count_before, ids_match, count_after) == ("nowy tekst", 1, True, 0)


def test_find_by_payload_matches_scalars_and_list_members():
    async def scenario(store):
        await store.upsert_raw(
            [
                point(7, ["a"], "doc-a", links=["https://a.example/x", "https://b.example/y"]),
                point(8, ["b"], "doc-b", links=["https://c.example/z"]),
                point(9, ["c"], "https://a.example/x"),
            ]
        )
        in_list = await store.find_by_payload("links", "https://b.example/y", 10)
        scalar = await store.find_by_payload("source_id", "https://a.example/x", 10)
        return len(in_list), len(scalar), await store.find_by_payload("links", "https://none.example", 10)

    assert run_with_store(scenario) == (1, 1, [])


def test_near_duplicate_is_found_for_a_copy_but_not_for_a_distinct_document():
    async def scenario(store):
        original = [point(index, ["x"], "doc-original") for index in (10, 11, 12, 13)]
        await store.upsert_raw(original)
        copy_vectors = [axis(index) for index in (10, 11, 12, 13)]
        distinct_vectors = [axis(index) for index in (20, 21, 22, 23)]
        return (
            await store.near_duplicate_document(copy_vectors, "doc-copy"),
            await store.near_duplicate_document(distinct_vectors, "doc-other"),
            await store.near_duplicate_document(copy_vectors, "doc-original"),
            await store.near_duplicate_document([], "doc-copy"),
        )

    assert run_with_store(scenario) == ("doc-original", None, None, None)


def test_invalid_collection_name_is_rejected():
    with pytest.raises(ValueError):
        VectorStore("evidence; DROP TABLE sources")
