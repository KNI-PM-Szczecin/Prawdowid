import logging

from app import db
from app.config import settings
from app.models import EvictionReport
from app.vector_store import VectorStore

logger = logging.getLogger(__name__)

PROTECTED_TIER = 1
FAST_ROTATION_TIER = 3

EVICTION_CANDIDATES_SQL = """
WITH active AS (
    SELECT * FROM document_metadata WHERE NOT is_deleted
),
topic_share AS (
    SELECT topic_tag, COUNT(*)::float / SUM(COUNT(*)) OVER () AS share
    FROM active GROUP BY topic_tag
)
SELECT a.chunk_id,
       DATE_PART('day', NOW() - a.added_at)
           * CASE WHEN a.tier = $1 THEN $2 ELSE 1.0 END * $3
       - a.read_count * $4
       + CASE WHEN t.share > $5 THEN $6 ELSE 0.0 END AS eviction_score
FROM active a
JOIN topic_share t ON t.topic_tag = a.topic_tag
WHERE a.tier > $7 AND (a.protected_until IS NULL OR NOW() > a.protected_until)
ORDER BY eviction_score DESC
LIMIT $8
"""


async def run_eviction(store: VectorStore) -> EvictionReport:
    """
    Evicts the highest-scoring unprotected chunks until the active set fits eviction_max_active_chunks.
    Score = effective_age * age_weight - read_count * read_weight (+ bonus for over-quota topics).
    The soft delete in PostgreSQL rolls back if the Qdrant hard delete fails, keeping both stores consistent.
    """
    async with db.pool().acquire() as connection, connection.transaction():
        active_count = await connection.fetchval("SELECT COUNT(*) FROM document_metadata WHERE NOT is_deleted")
        excess = active_count - settings.eviction_max_active_chunks
        if excess <= 0:
            return EvictionReport(active_before=active_count, evicted=0)

        rows = await connection.fetch(
            EVICTION_CANDIDATES_SQL,
            FAST_ROTATION_TIER,
            settings.eviction_tier3_age_multiplier,
            settings.eviction_age_weight,
            settings.eviction_read_weight,
            settings.eviction_topic_quota_share,
            settings.eviction_topic_overquota_bonus,
            PROTECTED_TIER,
            excess,
        )
        chunk_ids = [row["chunk_id"] for row in rows]
        if chunk_ids:
            await connection.execute(
                "UPDATE document_metadata SET is_deleted = TRUE WHERE chunk_id = ANY($1::uuid[])", chunk_ids
            )
            await store.delete(chunk_ids)

    logger.info("eviction: active_before=%d evicted=%d", active_count, len(chunk_ids))
    return EvictionReport(active_before=active_count, evicted=len(chunk_ids))
