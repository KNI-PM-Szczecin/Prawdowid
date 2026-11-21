from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from qdrant_client import AsyncQdrantClient, models

from app.config import settings
from app.embeddings import SparseVector

DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "bm25"
NIGHTLY_DELETED_THRESHOLD = 0.05
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


def build_filter(source_types: list[str] | None, published_after: datetime | None) -> models.Filter | None:
    """Payload filter applied inside each prefetch, so narrow filters do not starve the top-N pool."""
    conditions: list[models.Condition] = []
    if source_types:
        conditions.append(models.FieldCondition(key=SOURCE_TYPE_FIELD, match=models.MatchAny(any=source_types)))
    if published_after is not None:
        conditions.append(models.FieldCondition(key=PUBLISHED_AT_FIELD, range=models.DatetimeRange(gt=published_after)))
    return models.Filter(must=conditions) if conditions else None


class VectorStore:
    """Qdrant collection with static chunk text, vectors and filter fields; lifecycle state lives in PostgreSQL."""

    def __init__(self) -> None:
        self._client = AsyncQdrantClient(url=settings.qdrant_url)
        self._collection = settings.collection_name

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
        await self._client.upsert(
            self._collection,
            points=[
                models.PointStruct(
                    id=str(point.chunk_id),
                    vector={
                        DENSE_VECTOR_NAME: point.dense,
                        SPARSE_VECTOR_NAME: models.SparseVector(
                            indices=point.sparse.indices, values=point.sparse.values
                        ),
                    },
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
            ],
            wait=True,
        )

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
            RetrievedChunk(chunk_id=UUID(str(point.id)), text=point.payload["text"], fusion_score=point.score)
            for point in response.points
        ]

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
