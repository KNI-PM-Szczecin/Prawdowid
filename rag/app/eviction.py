import logging
from collections import Counter
from dataclasses import dataclass
from urllib.parse import urlparse
from uuid import UUID

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
SELECT a.chunk_id, a.source_id,
       DATE_PART('day', NOW() - a.added_at)
           * CASE WHEN a.tier = $1 THEN $2 ELSE 1.0 END * $3
       - a.read_count * $4
       + CASE WHEN t.share > $5 THEN $6 ELSE 0.0 END AS eviction_score
FROM active a
JOIN topic_share t ON t.topic_tag = a.topic_tag
WHERE a.tier > $7 AND (a.protected_until IS NULL OR NOW() > a.protected_until)
ORDER BY eviction_score DESC
"""

ACTIVE_DOCUMENTS_SQL = """
SELECT m.source_id, s.url, COUNT(*) AS active_chunks
FROM document_metadata m
JOIN sources s ON s.document_id = m.source_id
WHERE NOT m.is_deleted
GROUP BY m.source_id, s.url
"""


@dataclass(frozen=True)
class EvictionCandidate:
    chunk_id: UUID
    document_id: str


def select_evictions(
    candidates: list[EvictionCandidate],
    chunks_per_document: dict[str, int],
    domain_of_document: dict[str, str],
    excess: int,
    min_documents: int,
    min_domains: int,
) -> list[UUID]:
    """
    Picks up to `excess` chunks in candidate order, skipping any chunk whose removal would drop the last chunk
    of a document while the corpus is at min_documents, or the last document of a domain at min_domains.
    """
    remaining_chunks = dict(chunks_per_document)
    documents_per_domain = Counter(domain_of_document[document] for document in remaining_chunks)
    active_documents = len(remaining_chunks)
    selected: list[UUID] = []
    for candidate in candidates:
        if len(selected) == excess:
            break
        document = candidate.document_id
        if remaining_chunks.get(document, 0) == 0:
            continue
        removes_document = remaining_chunks[document] == 1
        if removes_document:
            domain = domain_of_document[document]
            removes_domain = documents_per_domain[domain] == 1
            if active_documents <= min_documents or (removes_domain and len(documents_per_domain) <= min_domains):
                continue
            active_documents -= 1
            documents_per_domain[domain] -= 1
            if documents_per_domain[domain] == 0:
                del documents_per_domain[domain]
        remaining_chunks[document] -= 1
        selected.append(candidate.chunk_id)
    return selected


async def run_eviction(store: VectorStore) -> EvictionReport:
    """
    Evicts the highest-scoring unprotected chunks until the active set fits eviction_max_active_chunks.
    Score = effective_age * age_weight - read_count * read_weight (+ bonus for over-quota topics).
    Never drops the corpus below eviction_min_documents / eviction_min_domains (brief minimum).
    The soft delete in PostgreSQL rolls back if the Qdrant hard delete fails, keeping both stores consistent.
    """
    chunk_ids: list[UUID] = []
    async with db.pool().acquire() as connection, connection.transaction():
        active_count = await connection.fetchval("SELECT COUNT(*) FROM document_metadata WHERE NOT is_deleted")
        excess = active_count - settings.eviction_max_active_chunks
        if excess <= 0:
            return EvictionReport(active_before=active_count, evicted=0)

        candidate_rows = await connection.fetch(
            EVICTION_CANDIDATES_SQL,
            FAST_ROTATION_TIER,
            settings.eviction_tier3_age_multiplier,
            settings.eviction_age_weight,
            settings.eviction_read_weight,
            settings.eviction_topic_quota_share,
            settings.eviction_topic_overquota_bonus,
            PROTECTED_TIER,
        )
        document_rows = await connection.fetch(ACTIVE_DOCUMENTS_SQL)
        chunk_ids = select_evictions(
            [EvictionCandidate(chunk_id=row["chunk_id"], document_id=row["source_id"]) for row in candidate_rows],
            {row["source_id"]: row["active_chunks"] for row in document_rows},
            {row["source_id"]: urlparse(row["url"]).hostname or "" for row in document_rows},
            excess,
            settings.eviction_min_documents,
            settings.eviction_min_domains,
        )
        if chunk_ids:
            await connection.execute(
                "UPDATE document_metadata SET is_deleted = TRUE WHERE chunk_id = ANY($1::uuid[])", chunk_ids
            )
            await store.delete(chunk_ids)

    logger.info("eviction: active_before=%d evicted=%d", active_count, len(chunk_ids))
    return EvictionReport(active_before=active_count, evicted=len(chunk_ids))
