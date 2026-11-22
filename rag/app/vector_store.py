import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

import asyncpg

from app import db
from app.config import settings

SOURCE_TYPE_FIELD = "source_type"
PUBLISHED_AT_FIELD = "published_at"
# Reciprocal rank fusion constant: the usual value from the original RRF paper.
RRF_K = 60
TABLE_PREFIX = "vec_"
COLLECTION_NAME = re.compile(r"[a-z_][a-z0-9_]*")

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS {table} (
    point_id UUID PRIMARY KEY,
    dense vector({dimension}) NOT NULL,
    lexical tsvector NOT NULL,
    source_id TEXT,
    source_type TEXT,
    published_at TIMESTAMPTZ,
    payload JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS {table}_dense ON {table} USING hnsw (dense vector_cosine_ops);
CREATE INDEX IF NOT EXISTS {table}_lexical ON {table} USING gin (lexical);
CREATE INDEX IF NOT EXISTS {table}_source ON {table} (source_id);
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
"""

UPSERT_SQL = """
INSERT INTO {table} (point_id, dense, lexical, source_id, source_type, published_at, payload)
VALUES ($1, $2::vector, to_tsvector('simple', $3), $4, $5, $6, $7::jsonb)
ON CONFLICT (point_id) DO UPDATE SET
    dense = EXCLUDED.dense, lexical = EXCLUDED.lexical, source_id = EXCLUDED.source_id,
    source_type = EXCLUDED.source_type, published_at = EXCLUDED.published_at, payload = EXCLUDED.payload
"""

# Both halves rank inside the same filter, so a narrow filter does not starve either candidate pool.
HYBRID_SQL = """
WITH dense_hits AS (
    SELECT point_id, row_number() OVER (ORDER BY dense <=> $1::vector) AS hit_rank
    FROM {table}
    WHERE ($2::text[] IS NULL OR source_type = ANY($2)) AND ($3::timestamptz IS NULL OR published_at > $3)
    ORDER BY dense <=> $1::vector
    LIMIT $4
),
lexical_hits AS (
    SELECT point_id, row_number() OVER (ORDER BY ts_rank_cd(lexical, query) DESC) AS hit_rank
    FROM {table}, to_tsquery('simple', $5) AS query
    WHERE lexical @@ query
      AND ($2::text[] IS NULL OR source_type = ANY($2)) AND ($3::timestamptz IS NULL OR published_at > $3)
    ORDER BY ts_rank_cd(lexical, query) DESC
    LIMIT $4
),
fused AS (
    SELECT point_id, SUM(1.0 / ({rrf_k} + hit_rank)) AS score
    FROM (SELECT * FROM dense_hits UNION ALL SELECT * FROM lexical_hits) AS hits
    GROUP BY point_id
)
SELECT fused.point_id, fused.score, vectors.payload::text AS payload
FROM fused JOIN {table} AS vectors USING (point_id)
ORDER BY fused.score DESC
LIMIT $4
"""

DENSE_ONLY_SQL = """
SELECT point_id, 1.0 / ({rrf_k} + row_number() OVER (ORDER BY dense <=> $1::vector)) AS score, payload::text AS payload
FROM {table}
WHERE ($2::text[] IS NULL OR source_type = ANY($2)) AND ($3::timestamptz IS NULL OR published_at > $3)
ORDER BY dense <=> $1::vector
LIMIT $4
"""

NEAREST_OTHER_DOCUMENT_SQL = """
SELECT neighbour.source_id, 1 - neighbour.distance AS cosine
FROM unnest($1::text[]) AS queries(vector)
CROSS JOIN LATERAL (
    SELECT source_id, dense <=> queries.vector::vector AS distance
    FROM {table}
    WHERE source_id IS DISTINCT FROM $2
    ORDER BY dense <=> queries.vector::vector
    LIMIT 1
) AS neighbour
"""


@dataclass(frozen=True)
class ChunkPoint:
    chunk_id: UUID
    source_id: str
    text: str
    topic_tag: str
    source_type: str
    published_at: datetime | None
    dense: list[float]
    lexical: list[str]


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: UUID
    text: str
    fusion_score: float
    payload: dict = field(default_factory=dict)


@dataclass(frozen=True)
class RawPoint:
    point_id: UUID
    dense: list[float]
    lexical: list[str]
    payload: dict


@dataclass(frozen=True)
class PayloadFilter:
    source_types: list[str] | None
    published_after: datetime | None


def build_filter(source_types: list[str] | None, published_after: datetime | None) -> PayloadFilter | None:
    if not source_types and published_after is None:
        return None
    return PayloadFilter(source_types=source_types or None, published_after=published_after)


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(format(value, ".8g") for value in vector) + "]"


def _tsquery(tokens: list[str]) -> str:
    return " | ".join(dict.fromkeys(tokens))


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


class VectorStore:
    """
    One pgvector table with dense vectors, stemmed text-search vectors and the JSON payload of every point. Used for
    the evidence corpus (lifecycle state in the neighbouring document_metadata table) and, with another collection
    name, for the disinformation incident catalog and the unresolved reports. Vectors, text and metadata live in the
    same database, so they cannot drift apart between environments.
    """

    def __init__(self, collection_name: str = settings.collection_name) -> None:
        if not COLLECTION_NAME.fullmatch(collection_name):
            raise ValueError(f"Invalid collection name: {collection_name!r}")
        self._table = TABLE_PREFIX + collection_name

    async def ensure_collection(self) -> None:
        await db.pool().execute(CREATE_TABLE_SQL.format(table=self._table, dimension=settings.dense_dim))

    async def upsert(self, points: list[ChunkPoint]) -> None:
        await self.upsert_raw(
            [
                RawPoint(
                    point_id=point.chunk_id,
                    dense=point.dense,
                    lexical=point.lexical,
                    payload={
                        "chunk_id": str(point.chunk_id),
                        "source_id": point.source_id,
                        "text": point.text,
                        "topic_tag": point.topic_tag,
                        SOURCE_TYPE_FIELD: point.source_type,
                        PUBLISHED_AT_FIELD: point.published_at.isoformat() if point.published_at else None,
                    },
                )
                for point in points
            ]
        )

    async def upsert_raw(self, points: list[RawPoint]) -> None:
        """Upserts points with a caller-defined payload; the payload must contain the embedded `text`."""
        rows = [
            (
                point.point_id,
                _vector_literal(point.dense),
                " ".join(point.lexical),
                point.payload.get("source_id"),
                point.payload.get(SOURCE_TYPE_FIELD),
                _parse_timestamp(point.payload.get(PUBLISHED_AT_FIELD)),
                json.dumps(point.payload),
            )
            for point in points
        ]
        async with db.pool().acquire() as connection, connection.transaction():
            await connection.executemany(
                UPSERT_SQL.format(table=self._table), rows, timeout=settings.vector_write_timeout_seconds
            )

    async def count(self) -> int:
        return await db.pool().fetchval(f"SELECT COUNT(*) FROM {self._table}")

    async def point_ids(self) -> list[UUID]:
        """Every point id in the table; used to reconcile with the lifecycle state in document_metadata."""
        rows = await db.pool().fetch(f"SELECT point_id FROM {self._table}")
        return [row["point_id"] for row in rows]

    async def find_by_payload(self, field: str, value: str, limit: int) -> list[dict]:
        """Payloads of points whose keyword field (a scalar or a list) contains the value; no vectors involved."""
        rows = await db.pool().fetch(
            f"""
            SELECT payload::text AS payload FROM {self._table}
            WHERE payload -> $1 = to_jsonb($2::text) OR payload -> $1 @> to_jsonb($2::text)
            LIMIT $3
            """,
            field,
            value,
            limit,
        )
        return [json.loads(row["payload"]) for row in rows]

    async def chunks_containing(self, source_id: str, phrases: list[str], limit: int) -> list[RetrievedChunk]:
        """Chunks of one document whose text contains any of the phrases (case-insensitive); no vectors involved."""
        rows = await db.pool().fetch(
            f"""
            SELECT point_id, payload::text AS payload FROM {self._table}
            WHERE source_id = $1 AND lower(payload ->> 'text') LIKE ANY($2::text[])
            LIMIT $3
            """,
            source_id,
            [f"%{phrase.lower()}%" for phrase in phrases],
            limit,
        )
        payloads = [(row["point_id"], json.loads(row["payload"])) for row in rows]
        return [
            RetrievedChunk(chunk_id=point_id, text=payload["text"], fusion_score=0.0, payload=payload)
            for point_id, payload in payloads
        ]

    async def hybrid_search(
        self, dense: list[float], lexical: list[str], limit: int, payload_filter: PayloadFilter | None
    ) -> list[RetrievedChunk]:
        source_types = payload_filter.source_types if payload_filter else None
        published_after = payload_filter.published_after if payload_filter else None
        arguments = [_vector_literal(dense), source_types, published_after, limit]
        if lexical:
            sql, arguments = HYBRID_SQL, [*arguments, _tsquery(lexical)]
        else:
            sql = DENSE_ONLY_SQL
        rows = await db.pool().fetch(sql.format(table=self._table, rrf_k=RRF_K), *arguments)
        chunks = []
        for row in rows:
            payload = json.loads(row["payload"])
            chunks.append(
                RetrievedChunk(
                    chunk_id=row["point_id"], text=payload["text"], fusion_score=float(row["score"]), payload=payload
                )
            )
        return chunks

    async def near_duplicate_document(self, dense_vectors: list[list[float]], source_id: str) -> str | None:
        """
        Id of another document that most of the given chunks point to as their nearest neighbour, with a high mean
        cosine: a re-fetched or lightly edited copy that the exact content hash cannot catch. Chunk boundaries of
        the copy may be shifted, so the rule uses the mean over all chunks, not a per-chunk threshold.
        All chunks go out in one query: a large document means hundreds of vectors, and per-chunk round trips made
        ingesting it minutes instead of seconds.
        """
        if not dense_vectors:
            return None
        rows = await db.pool().fetch(
            NEAREST_OTHER_DOCUMENT_SQL.format(table=self._table),
            [_vector_literal(vector) for vector in dense_vectors],
            source_id,
        )
        if not rows:
            return None
        matches = Counter(row["source_id"] for row in rows)
        # A chunk with no neighbour at all counts as cosine 0, as an unmatched chunk does for the document's mean.
        mean_cosine = sum(float(row["cosine"]) for row in rows) / len(dense_vectors)
        document_id, count = matches.most_common(1)[0]
        share = count / len(dense_vectors)
        if share >= settings.near_duplicate_min_share and mean_cosine >= settings.near_duplicate_min_mean_cosine:
            return document_id
        return None

    async def delete(self, chunk_ids: list[UUID]) -> None:
        await db.pool().execute(f"DELETE FROM {self._table} WHERE point_id = ANY($1::uuid[])", chunk_ids)

    async def optimize(self) -> None:
        """Reclaims the space of deleted rows and refreshes planner statistics, which the HNSW scans rely on."""
        await db.pool().execute(f"VACUUM (ANALYZE) {self._table}", timeout=settings.vector_write_timeout_seconds)


STORE_ERRORS = (asyncpg.PostgresError, asyncpg.InterfaceError, OSError)
