from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from qdrant_client import AsyncQdrantClient, models

from app.config import settings
from app.embeddings import SparseVector

DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "bm25"
NIGHTLY_DELETED_THRESHOLD = 0.05
SCROLL_PAGE_SIZE = 1000
SOURCE_TYPE_FIELD = "source_type"
PUBLISHED_AT_FIELD = "published_at"


@dataclass(frozen=True)
class ChunkPoint:
    chunk_id: UUID
    source_id: str
    text: str
    topic_tag: str
    source_type: str
    published_at: datetime | None
    dense: list[float]
    sparse: SparseVector


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
    sparse: SparseVector
    payload: dict


def build_filter(source_types: list[str] | None, published_after: datetime | None) -> models.Filter | None:
    """Payload filter applied inside each prefetch, so narrow filters do not starve the top-N pool."""
    conditions: list[models.Condition] = []
    if source_types:
        conditions.append(models.FieldCondition(key=SOURCE_TYPE_FIELD, match=models.MatchAny(any=source_types)))
    if published_after is not None:
        conditions.append(models.FieldCondition(key=PUBLISHED_AT_FIELD, range=models.DatetimeRange(gt=published_after)))
    return models.Filter(must=conditions) if conditions else None


class VectorStore:
    """
    One Qdrant collection with static text, dense + sparse vectors and payload. Used for the evidence corpus
    (lifecycle state in PostgreSQL) and, with another collection name, for the disinformation incident catalog.
    """

    def __init__(self, collection_name: str = settings.collection_name) -> None:
        self._client = AsyncQdrantClient(url=settings.qdrant_url, timeout=settings.qdrant_timeout_seconds)
        self._collection = collection_name

    async def ensure_collection(self) -> None:
        if not await self._client.collection_exists(self._collection):
            await self._client.create_collection(
                self._collection,
                vectors_config={
                    DENSE_VECTOR_NAME: models.VectorParams(size=settings.dense_dim, distance=models.Distance.COSINE)
                },
                sparse_vectors_config={SPARSE_VECTOR_NAME: models.SparseVectorParams(modifier=models.Modifier.IDF)},
            )
        await self._client.create_payload_index(
            self._collection, SOURCE_TYPE_FIELD, field_schema=models.PayloadSchemaType.KEYWORD
        )
        await self._client.create_payload_index(
            self._collection, PUBLISHED_AT_FIELD, field_schema=models.PayloadSchemaType.DATETIME
        )

    async def upsert(self, points: list[ChunkPoint]) -> None:
        await self.upsert_raw(
            [
                RawPoint(
                    point_id=point.chunk_id,
                    dense=point.dense,
                    sparse=point.sparse,
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
        await self._client.upsert(
            self._collection,
            points=[
                models.PointStruct(
                    id=str(point.point_id),
                    vector={
                        DENSE_VECTOR_NAME: point.dense,
                        SPARSE_VECTOR_NAME: models.SparseVector(
                            indices=point.sparse.indices, values=point.sparse.values
                        ),
                    },
                    payload=point.payload,
                )
                for point in points
            ],
            wait=True,
        )

    async def count(self) -> int:
        return (await self._client.count(self._collection, exact=True)).count

    async def point_ids(self) -> list[UUID]:
        """Every point id in the collection, without payloads or vectors; used to reconcile with PostgreSQL."""
        ids: list[UUID] = []
        offset = None
        while True:
            points, offset = await self._client.scroll(
                self._collection, limit=SCROLL_PAGE_SIZE, offset=offset, with_payload=False, with_vectors=False
            )
            ids.extend(UUID(str(point.id)) for point in points)
            if offset is None:
                return ids

    async def hybrid_search(
        self, dense: list[float], sparse: SparseVector, limit: int, payload_filter: models.Filter | None
    ) -> list[RetrievedChunk]:
        response = await self._client.query_points(
            self._collection,
            prefetch=[
                models.Prefetch(query=dense, using=DENSE_VECTOR_NAME, limit=limit, filter=payload_filter),
                models.Prefetch(
                    query=models.SparseVector(indices=sparse.indices, values=sparse.values),
                    using=SPARSE_VECTOR_NAME,
                    limit=limit,
                    filter=payload_filter,
                ),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            with_payload=True,
            limit=limit,
        )
        return [
            RetrievedChunk(
                chunk_id=UUID(str(point.id)),
                text=point.payload["text"],
                fusion_score=point.score,
                payload=point.payload,
            )
            for point in response.points
        ]

    async def near_duplicate_document(self, dense_vectors: list[list[float]], source_id: str) -> str | None:
        """
        Id of another document that most of the given chunks point to as their nearest neighbour, with a high mean
        cosine: a re-fetched or lightly edited copy that the exact content hash cannot catch. Chunk boundaries of
        the copy may be shifted, so the rule uses the mean over all chunks, not a per-chunk threshold.
        All chunk queries go out as one batch: a large document means hundreds of vectors, and per-chunk
        round trips made ingesting it minutes instead of seconds.
        """
        if not dense_vectors:
            return None
        other_documents = models.Filter(
            must_not=[models.FieldCondition(key="source_id", match=models.MatchValue(value=source_id))]
        )
        requests = [
            models.QueryRequest(
                query=vector,
                using=DENSE_VECTOR_NAME,
                filter=other_documents,
                limit=1,
                with_payload=["source_id"],
            )
            for vector in dense_vectors
        ]
        responses = await self._client.query_batch_points(self._collection, requests=requests)
        matches: Counter[str] = Counter()
        best_scores: list[float] = []
        for response in responses:
            if response.points:
                matches[response.points[0].payload["source_id"]] += 1
                best_scores.append(response.points[0].score)
            else:
                best_scores.append(0.0)
        if not matches:
            return None
        document_id, count = matches.most_common(1)[0]
        share = count / len(dense_vectors)
        mean_cosine = sum(best_scores) / len(best_scores)
        if share >= settings.near_duplicate_min_share and mean_cosine >= settings.near_duplicate_min_mean_cosine:
            return document_id
        return None

    async def delete(self, chunk_ids: list[UUID]) -> None:
        await self._client.delete(
            self._collection,
            points_selector=models.PointIdsList(points=[str(chunk_id) for chunk_id in chunk_ids]),
            wait=True,
        )

    async def optimize(self) -> None:
        """Lowers the vacuum threshold, which also wakes the optimizer to merge segments and rebuild HNSW."""
        await self._client.update_collection(
            self._collection,
            optimizers_config=models.OptimizersConfigDiff(deleted_threshold=NIGHTLY_DELETED_THRESHOLD),
        )

    async def close(self) -> None:
        await self._client.close()
