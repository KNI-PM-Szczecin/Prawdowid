import asyncio
import hashlib
import re
from uuid import uuid4

from app import db
from app.catalog import qualify
from app.config import settings
from app.embeddings import EmbeddingModels
from app.models import DocumentIn, IngestResult
from app.vector_store import ChunkPoint, VectorStore

PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")
WHITESPACE = re.compile(r"\s+")


class DuplicateDocumentError(ValueError):
    """Another active document already holds this text: exactly (hash) or nearly (embedding similarity)."""

    def __init__(self, document_id: str, duplicate_of: str, near: bool = False) -> None:
        super().__init__(f"Document {document_id} {'nearly ' if near else ''}duplicates {duplicate_of}")
        self.document_id = document_id
        self.duplicate_of = duplicate_of
        self.near = near


def content_hash(text: str) -> str:
    return hashlib.sha256(WHITESPACE.sub(" ", text).strip().casefold().encode("utf-8")).hexdigest()


def _split_long(text: str, max_chars: int, overlap: int) -> list[str]:
    step = max_chars - overlap
    return [text[start : start + max_chars] for start in range(0, max(len(text) - overlap, 1), step)]


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


async def ingest_document(
    document: DocumentIn, models: EmbeddingModels, store: VectorStore, allow_near_duplicate: bool = False
) -> IngestResult:
    """
    Chunks, embeds and indexes one document. Re-ingesting a document_id replaces its previous chunks
    after the new ones are stored, so search never sees a document with zero chunks.
    `allow_near_duplicate` is reserved for curated seed documents: a dated excerpt must be indexed even when a
    full, undated copy from the scraper is already present, because only the dated one may serve as evidence.
    """
    source = qualify(document.source)
    text_hash = content_hash(document.text)
    duplicate_of = await db.find_duplicate_document(text_hash, source.document_id)
    if duplicate_of is not None:
        raise DuplicateDocumentError(source.document_id, duplicate_of)
    previous_ids = await db.active_chunk_ids_for_document(source.document_id)

    texts = chunk_text(document.text, settings.chunk_max_chars, settings.chunk_overlap_chars)
    dense_vectors, sparse_vectors = await asyncio.to_thread(models.embed_documents, texts)
    if not allow_near_duplicate:
        near_duplicate_of = await store.near_duplicate_document(dense_vectors, source.document_id)
        if near_duplicate_of is not None:
            raise DuplicateDocumentError(source.document_id, near_duplicate_of, near=True)
    chunk_ids = [uuid4() for _ in texts]

    await store.upsert(
        [
            ChunkPoint(
                chunk_id=chunk_id,
                source_id=source.document_id,
                text=text,
                topic_tag=source.topic_tag,
                source_type=source.source_type,
                published_at=source.published_at,
                dense=dense,
                sparse=sparse,
            )
            for chunk_id, text, dense, sparse in zip(chunk_ids, texts, dense_vectors, sparse_vectors, strict=True)
        ]
    )
    await db.upsert_source_with_chunks(source, text_hash, chunk_ids)

    if previous_ids:
        await store.delete(previous_ids)
        await db.mark_chunks_deleted(previous_ids)

    return IngestResult(
        document_id=source.document_id,
        chunks_indexed=len(chunk_ids),
        chunks_replaced=len(previous_ids),
        in_catalog=source.in_catalog,
    )


async def delete_document_chunks(document_id: str, store: VectorStore) -> int:
    """Hard delete in Qdrant, soft delete in Postgres; returns how many chunks were active (0 = nothing to delete)."""
    chunk_ids = await db.active_chunk_ids_for_document(document_id)
    if chunk_ids:
        await store.delete(chunk_ids)
        await db.mark_chunks_deleted(chunk_ids)
    return len(chunk_ids)
