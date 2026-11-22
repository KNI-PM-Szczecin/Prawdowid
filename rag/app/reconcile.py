import logging

from app import db
from app.models import ReconcileReport
from app.vector_store import VectorStore

logger = logging.getLogger(__name__)

DELETE_BATCH_SIZE = 500


async def reconcile_vectors(store: VectorStore, include_unknown: bool = False) -> ReconcileReport:
    """
    Removes vector rows that PostgreSQL no longer counts as active, and soft-deletes active metadata that has no
    vector. PostgreSQL is the lifecycle authority (soft delete, eviction, prune); a point it marks deleted is stale
    and would only cost reranker time before being dropped at the metadata join. Points PostgreSQL has never seen are reported, and deleted only on request:
    an import in progress writes the vectors first, so an unknown point may simply be seconds old.
    """
    states = await db.chunk_states()
    stale = []
    unknown = []
    vector_ids = await store.point_ids()
    for point_id in vector_ids:
        if point_id not in states:
            unknown.append(point_id)
        elif states[point_id]:
            stale.append(point_id)
    # The other direction: an active chunk without a vector is an orphan (an import writes the vectors first, so this
    # never holds during a healthy import). Left alone it would make imports skip the document as already present
    # and block an identical document as a duplicate, so it would never get vectors again.
    present = set(vector_ids)
    orphans = [chunk_id for chunk_id, deleted in states.items() if not deleted and chunk_id not in present]
    if orphans:
        await db.mark_chunks_deleted(orphans)
    to_delete = stale + unknown if include_unknown else stale
    for start in range(0, len(to_delete), DELETE_BATCH_SIZE):
        await store.delete(to_delete[start : start + DELETE_BATCH_SIZE])
    logger.info(
        "vector reconcile: %d stale points deleted, %d unknown points %s, %d metadata orphans soft-deleted",
        len(stale),
        len(unknown),
        "deleted" if include_unknown else "kept",
        len(orphans),
    )
    return ReconcileReport(
        stale_deleted=len(stale),
        unknown=len(unknown),
        unknown_deleted=len(unknown) if include_unknown else 0,
        orphan_metadata_deleted=len(orphans),
        active_chunks=sum(1 for chunk_id, deleted in states.items() if not deleted and chunk_id in present),
    )
