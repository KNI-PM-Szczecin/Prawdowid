import logging
from pathlib import Path
from uuid import UUID

import asyncpg

from app.config import settings
from app.models import SourceIn

logger = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
EMPTY_CORPUS_VERSION = "empty"

_pool: asyncpg.Pool | None = None


async def connect() -> None:
    global _pool
    _pool = await asyncpg.create_pool(settings.postgres_dsn)
    async with _pool.acquire() as connection:
        await connection.execute(SCHEMA_PATH.read_text(encoding="utf-8"))


async def close() -> None:
    if _pool is not None:
        await _pool.close()


def pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool is not initialised")
    return _pool


async def upsert_source_with_chunks(source: SourceIn, chunk_ids: list[UUID]) -> None:
    async with pool().acquire() as connection, connection.transaction():
        await connection.execute(
            """
            INSERT INTO sources (document_id, title, publisher, url, published_at, fetched_at, license, source_type)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (document_id) DO UPDATE SET
                title = EXCLUDED.title, publisher = EXCLUDED.publisher, url = EXCLUDED.url,
                published_at = EXCLUDED.published_at, fetched_at = EXCLUDED.fetched_at,
                license = EXCLUDED.license, source_type = EXCLUDED.source_type
            """,
            source.document_id,
            source.title,
            source.publisher,
            str(source.url),
            source.published_at,
            source.fetched_at,
            source.license,
            source.source_type,
        )
        await connection.executemany(
            """
            INSERT INTO document_metadata (chunk_id, source_id, topic_tag, tier, reliability, protected_until)
            VALUES ($1, $2, $3, $4, $5, NOW() + make_interval(days => $6))
            """,
            [
                (
                    chunk_id,
                    source.document_id,
                    source.topic_tag,
                    source.tier,
                    source.reliability,
                    settings.protection_days,
                )
                for chunk_id in chunk_ids
            ],
        )


async def active_chunk_ids_for_document(document_id: str) -> list[UUID]:
    rows = await pool().fetch(
        "SELECT chunk_id FROM document_metadata WHERE source_id = $1 AND NOT is_deleted", document_id
    )
    return [row["chunk_id"] for row in rows]


async def list_sources() -> list[asyncpg.Record]:
    return await pool().fetch(
        """
        SELECT s.*, COUNT(m.chunk_id) FILTER (WHERE NOT m.is_deleted) AS active_chunks
        FROM sources s
        LEFT JOIN document_metadata m ON m.source_id = s.document_id
        GROUP BY s.document_id
        ORDER BY s.document_id
        """
    )


async def corpus_version() -> str:
    """Changes whenever chunks are added or removed; lets agent/ tie a verdict to a corpus snapshot."""
    row = await pool().fetchrow(
        """
        SELECT COUNT(*) FILTER (WHERE NOT is_deleted) AS active, COUNT(*) AS total, MAX(added_at) AS last_added
        FROM document_metadata
        """
    )
    if row["last_added"] is None:
        return EMPTY_CORPUS_VERSION
    return f"{row['last_added']:%Y%m%dT%H%M%S}-{row['active']}-{row['total']}"


async def mark_chunks_deleted(chunk_ids: list[UUID]) -> None:
    await pool().execute("UPDATE document_metadata SET is_deleted = TRUE WHERE chunk_id = ANY($1::uuid[])", chunk_ids)


async def fetch_passage_metadata(chunk_ids: list[UUID]) -> dict[UUID, asyncpg.Record]:
    rows = await pool().fetch(
        """
        SELECT m.chunk_id, m.tier, m.reliability,
               s.document_id, s.title, s.publisher, s.url, s.published_at, s.fetched_at, s.license, s.source_type
        FROM document_metadata m
        JOIN sources s ON s.document_id = m.source_id
        WHERE m.chunk_id = ANY($1::uuid[]) AND NOT m.is_deleted
        """,
        chunk_ids,
    )
    return {row["chunk_id"]: row for row in rows}


async def register_reads(chunk_ids: list[UUID]) -> None:
    """Best-effort read counter; a failure here must never affect the search response."""
    try:
        await pool().execute(
            """
            UPDATE document_metadata
            SET read_count = read_count + 1, last_accessed_at = NOW()
            WHERE chunk_id = ANY($1::uuid[])
            """,
            chunk_ids,
        )
    except (asyncpg.PostgresError, OSError):
        logger.exception("Failed to register reads for %d chunks", len(chunk_ids))
