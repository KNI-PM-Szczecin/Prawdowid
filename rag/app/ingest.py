import asyncio
import re
from uuid import uuid4

from app import db
from app.config import settings
from app.embeddings import EmbeddingModels
from app.models import DocumentIn, IngestResult
from app.vector_store import ChunkPoint, VectorStore

PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")
WHITESPACE = re.compile(r"\s+")


def _split_long(text: str, max_chars: int, overlap: int) -> list[str]:
    step = max_chars - overlap
    return [text[start:start + max_chars] for start in range(0, max(len(text) - overlap, 1), step)]


def chunk_text(text: str, max_chars: int, overlap: int) -> list[str]:
    """Packs whole paragraphs into chunks up to max_chars; only oversize paragraphs are cut with overlap."""
    chunks: list[str] = []
    current: list[str] = []
    current_length = 0
    for raw_paragraph in PARAGRAPH_SPLIT.split(text):
        paragraph = WHITESPACE.sub(" ", raw_paragraph).strip()
        if not paragraph:
            continue
        if len(paragraph) > max_chars:
            if current:
                chunks.append(" ".join(current))
                current, current_length = [], 0
            chunks.extend(_split_long(paragraph, max_chars, overlap))
            continue
        if current and current_length + len(paragraph) + 1 > max_chars:
            chunks.append(" ".join(current))
            current, current_length = [], 0
        current.append(paragraph)
        current_length += len(paragraph) + 1
    if current:
        chunks.append(" ".join(current))
    return chunks


async def ingest_document(document: DocumentIn, models: EmbeddingModels, store: VectorStore) -> IngestResult:
    """
    Chunks, embeds and indexes one document. Re-ingesting a source_id replaces its previous chunks
    after the new ones are stored, so search never sees a source with zero chunks.
    """
    source = document.source
    previous_ids = await db.active_chunk_ids_for_source(source.source_id)

    texts = chunk_text(document.text, settings.chunk_max_chars, settings.chunk_overlap_chars)
    dense_vectors, sparse_vectors = await asyncio.to_thread(models.embed_documents, texts)
    chunk_ids = [uuid4() for _ in texts]

    await store.upsert(
        [
            ChunkPoint(
                chunk_id=chunk_id, source_id=source.source_id, text=text,
                topic_tag=source.topic_tag, dense=dense, sparse=sparse,
            )
            for chunk_id, text, dense, sparse in zip(chunk_ids, texts, dense_vectors, sparse_vectors)
        ]
    )
    await db.upsert_source_with_chunks(source, chunk_ids)

    if previous_ids:
        await store.delete(previous_ids)
        await db.mark_chunks_deleted(previous_ids)

    return IngestResult(source_id=source.source_id, chunks_indexed=len(chunk_ids), chunks_replaced=len(previous_ids))
