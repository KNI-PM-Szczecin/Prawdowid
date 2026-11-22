import logging

from app import db
from app.models import ReconcileReport
from app.vector_store import VectorStore

logger = logging.getLogger(__name__)

DELETE_BATCH_SIZE = 500


async def reconcile_vectors(store: VectorStore, include_unknown: bool = False) -> ReconcileReport:
    """
    Removes vector rows that PostgreSQL no longer counts as active. PostgreSQL is the lifecycle authority
    (soft delete, eviction, prune); a point it marks deleted is stale and would only cost reranker time before
    being dropped at the metadata join. Points PostgreSQL has never seen are reported, and deleted only on request:
    an import in progress writes the vectors first, so an unknown point may simply be seconds old.
    """
    states = await db.chunk_states()
    stale = []
    unknown = []
    for point_id in await store.point_ids():
        if point_id not in states:
            unknown.append(point_id)
        elif states[point_id]:
            stale.append(point_id)
    to_delete = stale + unknown if include_unknown else stale
    for start in range(0, len(to_delete), DELETE_BATCH_SIZE):
        await store.delete(to_delete[start : start + DELETE_BATCH_SIZE])
    logger.info(
        "vector reconcile: %d stale points deleted, %d unknown points %s",
        len(stale),
        len(unknown),
        "deleted" if include_unknown else "kept",
    )
    return ReconcileReport(
        stale_deleted=len(stale),
        unknown=len(unknown),
        unknown_deleted=len(unknown) if include_unknown else 0,
        active_chunks=sum(1 for deleted in states.values() if not deleted),
    )
