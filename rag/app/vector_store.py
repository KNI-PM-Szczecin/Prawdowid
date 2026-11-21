from dataclasses import dataclass
from uuid import UUID

from qdrant_client import AsyncQdrantClient, models

from app.config import settings
from app.embeddings import SparseVector

DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "bm25"
NIGHTLY_DELETED_THRESHOLD = 0.05


@dataclass(frozen=True)
class ChunkPoint:
    chunk_id: UUID
    source_id: str
    text: str
    topic_tag: str
    dense: list[float]
    sparse: SparseVector


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: UUID
    text: str
    fusion_score: float


class VectorStore:
    """Qdrant collection holding only static chunk text and vectors; lifecycle state lives in PostgreSQL."""

    def __init__(self) -> None:
        self._client = AsyncQdrantClient(url=settings.qdrant_url)
        self._collection = settings.collection_name

    async def ensure_collection(self) -> None:
        if await self._client.collection_exists(self._collection):
            return
        await self._client.create_collection(
            self._collection,
            vectors_config={
                DENSE_VECTOR_NAME: models.VectorParams(size=settings.dense_dim, distance=models.Distance.COSINE)
            },
            sparse_vectors_config={SPARSE_VECTOR_NAME: models.SparseVectorParams(modifier=models.Modifier.IDF)},
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
                    },
                )
                for point in points
            ],
            wait=True,
        )

    async def hybrid_search(self, dense: list[float], sparse: SparseVector, limit: int) -> list[RetrievedChunk]:
        response = await self._client.query_points(
            self._collection,
            prefetch=[
                models.Prefetch(query=dense, using=DENSE_VECTOR_NAME, limit=limit),
                models.Prefetch(
                    query=models.SparseVector(indices=sparse.indices, values=sparse.values),
                    using=SPARSE_VECTOR_NAME,
                    limit=limit,
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
