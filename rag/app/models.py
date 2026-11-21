from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl

Tier = Literal[1, 2, 3]
Reliability = Literal["wysoka", "srednia", "niska"]
SourceType = Literal["urzedowe", "wtorne"]

CLAIM_MAX_CHARS = 2000
DOCUMENT_MAX_CHARS = 500_000
INGEST_BATCH_MAX_DOCUMENTS = 200


class SourceIn(BaseModel):
    source_id: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1)
    publisher: str = Field(min_length=1)
    url: HttpUrl
    published_at: date
    retrieved_at: date
    license: str = Field(min_length=1)
    source_type: SourceType
    tier: Tier = 2
    reliability: Reliability
    topic_tag: str = Field(min_length=1, max_length=100)


class DocumentIn(BaseModel):
    source: SourceIn
    text: str = Field(min_length=1, max_length=DOCUMENT_MAX_CHARS)


class IngestRequest(BaseModel):
    documents: list[DocumentIn] = Field(min_length=1, max_length=INGEST_BATCH_MAX_DOCUMENTS)


class IngestResult(BaseModel):
    source_id: str
    chunks_indexed: int
    chunks_replaced: int


class SearchRequest(BaseModel):
    claim: str = Field(min_length=3, max_length=CLAIM_MAX_CHARS)
    top_k: int | None = Field(default=None, ge=1)


class ExpandedQueries(BaseModel):
    original: str
    negative: str
    neutral: str
    method: Literal["llm", "rules"]


class SourceOut(BaseModel):
    source_id: str
    title: str
    publisher: str
    url: str
    published_at: date
    retrieved_at: date
    license: str
    source_type: SourceType


class Evidence(BaseModel):
    chunk_id: UUID
    text: str
    rerank_score: float
    tier: Tier
    reliability: Reliability
    topic_tag: str
    source: SourceOut
    suspicious_instructions: bool


class SearchResponse(BaseModel):
    queries: ExpandedQueries
    evidence: list[Evidence]
    context_xml: str
    elapsed_ms: int


class SourceAuditEntry(SourceOut):
    tier: Tier | None
    reliability: Reliability | None
    active_chunks: int


class DeletionReport(BaseModel):
    source_id: str
    chunks_deleted: int


class EvictionReport(BaseModel):
    active_before: int
    evicted: int
