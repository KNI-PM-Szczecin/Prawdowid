from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl
from pydantic.alias_generators import to_camel

Tier = Literal[1, 2, 3]
Reliability = Literal["high", "medium", "low"]
SourceType = Literal["official", "secondary", "factcheck", "incident"]
PassageFlag = Literal["suspected_injection"]

QUERY_MAX_CHARS = 5000
DOCUMENT_MAX_CHARS = 500_000
INGEST_BATCH_MAX_DOCUMENTS = 200


class ApiModel(BaseModel):
    """camelCase on the wire (CONTRACT.md), snake_case in Python."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class SourceIn(ApiModel):
    document_id: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1)
    publisher: str = Field(min_length=1)
    url: HttpUrl
    published_at: date | None = None
    fetched_at: date
    license: str | None = None
    source_type: SourceType
    tier: Tier = 2
    reliability: Reliability
    topic_tag: str = Field(min_length=1, max_length=100)


class DocumentIn(ApiModel):
    source: SourceIn
    text: str = Field(min_length=1, max_length=DOCUMENT_MAX_CHARS)


class IngestRequest(ApiModel):
    documents: list[DocumentIn] = Field(min_length=1, max_length=INGEST_BATCH_MAX_DOCUMENTS)


class IngestResult(ApiModel):
    document_id: str
    chunks_indexed: int
    chunks_replaced: int


class SearchFilters(ApiModel):
    source_types: list[SourceType] | None = None
    published_after: date | None = None


class SearchRequest(ApiModel):
    query: str = Field(min_length=3, max_length=QUERY_MAX_CHARS)
    top_k: int | None = Field(default=None, ge=1)
    filters: SearchFilters | None = None


class ExpandedQueries(ApiModel):
    original: str
    negative: str
    neutral: str
    method: Literal["llm", "rules"]


class Passage(ApiModel):
    document_id: str
    title: str
    publisher: str
    published_at: date | None
    fetched_at: date
    url: str
    license: str | None
    source_type: SourceType
    passage: str
    score: float
    flags: list[PassageFlag]
    chunk_id: UUID
    tier: Tier
    reliability: Reliability


class SearchResponse(ApiModel):
    results: list[Passage]
    corpus_version: str
    context_xml: str
    expanded_queries: ExpandedQueries
    elapsed_ms: int


class SourceAuditEntry(ApiModel):
    document_id: str
    title: str
    publisher: str
    domain: str
    url: str
    source_type: SourceType
    license: str | None
    published_at: date | None
    fetched_at: date
    active_chunks: int


class HealthResponse(ApiModel):
    status: Literal["ok"]
    corpus_version: str


class DeletionReport(ApiModel):
    document_id: str
    chunks_deleted: int


class EvictionReport(ApiModel):
    active_before: int
    evicted: int
