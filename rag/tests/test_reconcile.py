import asyncio
from uuid import uuid4

from app import db
from app.reconcile import reconcile_vectors

ACTIVE, STALE, UNKNOWN, ORPHAN = uuid4(), uuid4(), uuid4(), uuid4()


class FakeStore:
    def __init__(self):
        self.points = [ACTIVE, STALE, UNKNOWN]
        self.deleted: list = []

    async def point_ids(self):
        return list(self.points)

    async def delete(self, chunk_ids):
        self.deleted.extend(chunk_ids)
        self.points = [point for point in self.points if point not in chunk_ids]


def _states(monkeypatch):
    async def chunk_states():
        return {ACTIVE: False, STALE: True}

    async def mark_chunks_deleted(chunk_ids):
        return None

    monkeypatch.setattr(db, "chunk_states", chunk_states)
    monkeypatch.setattr(db, "mark_chunks_deleted", mark_chunks_deleted)


def test_reconcile_deletes_only_points_postgres_marks_deleted(monkeypatch):
    _states(monkeypatch)
    store = FakeStore()
    report = asyncio.run(reconcile_vectors(store))
    assert store.deleted == [STALE]
    assert (report.stale_deleted, report.unknown, report.unknown_deleted, report.active_chunks) == (1, 1, 0, 1)
    assert store.points == [ACTIVE, UNKNOWN]


def test_reconcile_can_also_drop_points_postgres_never_saw(monkeypatch):
    _states(monkeypatch)
    store = FakeStore()
    report = asyncio.run(reconcile_vectors(store, include_unknown=True))
    assert sorted(map(str, store.deleted)) == sorted(map(str, [STALE, UNKNOWN]))
    assert (report.stale_deleted, report.unknown_deleted) == (1, 1)
    assert store.points == [ACTIVE]


def test_reconcile_soft_deletes_active_metadata_that_has_no_vector(monkeypatch):
    marked: list = []

    async def chunk_states():
        return {ACTIVE: False, ORPHAN: False, STALE: True}

    async def mark_chunks_deleted(chunk_ids):
        marked.extend(chunk_ids)

    monkeypatch.setattr(db, "chunk_states", chunk_states)
    monkeypatch.setattr(db, "mark_chunks_deleted", mark_chunks_deleted)
    report = asyncio.run(reconcile_vectors(FakeStore()))
    assert marked == [ORPHAN]
    assert (report.orphan_metadata_deleted, report.active_chunks) == (1, 1)
