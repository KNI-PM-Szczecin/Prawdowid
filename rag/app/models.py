from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, HttpUrl
from pydantic.alias_generators import to_camel

from app.config import settings

Tier = Literal[1, 2, 3]
Reliability = Literal["high", "medium", "low"]
SourceType = Literal["official", "secondary", "factcheck", "incident"]
PassageFlag = Literal["suspected_injection"]

QUERY_MAX_CHARS = 5000
DOCUMENT_MAX_CHARS = 500_000
INGEST_BATCH_MAX_DOCUMENTS = 200


def _assume_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


# Accepts ISO 8601 date or timestamp; a value without an offset is taken as UTC.
Timestamp = Annotated[datetime, AfterValidator(_assume_utc)]


class ApiModel(BaseModel):
    """camelCase on the wire (CONTRACT.md), snake_case in Python."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class SourceIn(ApiModel):
    document_id: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1)
    publisher: str = Field(min_length=1)
    url: HttpUrl
    published_at: Timestamp | None = None
    fetched_at: Timestamp
    license: str | None = None
    # Left empty, these come from the source catalog by the URL's domain (app/catalog.py).
    source_type: SourceType | None = None
    tier: Tier | None = None
    reliability: Reliability | None = None
    topic_tag: str = Field(min_length=1, max_length=100)


class QualifiedSource(SourceIn):
    """SourceIn after catalog qualification: metadata complete, origin of the qualification recorded."""

    source_type: SourceType
    tier: Tier
    reliability: Reliability
    in_catalog: bool


class CatalogEntry(ApiModel):
    publisher: str
    domains: list[str] = Field(min_length=1)
    source_type: SourceType
    tier: Tier
    reliability: Reliability
    qualification: str


class SourceCatalog(ApiModel):
    version: str
    note: str
    rules: dict[str, str]
    entries: list[CatalogEntry]


class DocumentIn(ApiModel):
    source: SourceIn
    text: str = Field(min_length=1, max_length=DOCUMENT_MAX_CHARS)


class IngestRequest(ApiModel):
    documents: list[DocumentIn] = Field(min_length=1, max_length=INGEST_BATCH_MAX_DOCUMENTS)


class IngestResult(ApiModel):
    document_id: str
    chunks_indexed: int
    chunks_replaced: int
    in_catalog: bool


class SearchFilters(ApiModel):
    source_types: list[SourceType] | None = None
    published_after: Timestamp | None = None


class SearchRequest(ApiModel):
    query: str = Field(min_length=3, max_length=QUERY_MAX_CHARS)
    top_k: int = Field(default=settings.rerank_top_k, ge=1, le=settings.rerank_top_k_max)
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
    published_at: Timestamp | None
    fetched_at: Timestamp
    url: str
    license: str | None
    source_type: SourceType
    passage: str
    score: float
    flags: list[PassageFlag]
    chunk_id: UUID
    tier: Tier
    reliability: Reliability


INCIDENT_BATCH_MAX = 500
CAMPAIGN_CATEGORY = "possible_disinformation_campaign"


class IncidentIn(ApiModel):
    """One known disinformation case, e.g. an EUvsDisinfo database entry or a record from the organizer's base."""

    incident_id: str = Field(min_length=1, max_length=255)
    source: str = Field(min_length=1, max_length=100, description="Catalog name, e.g. euvsdisinfo")
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1, max_length=DOCUMENT_MAX_CHARS, description="The disinformation claim")
    url: HttpUrl
    published_at: Timestamp | None = None
    countries: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    license: str | None = None


class IncidentIngestRequest(ApiModel):
    incidents: list[IncidentIn] = Field(min_length=1, max_length=INCIDENT_BATCH_MAX)


class IncidentIngestResult(ApiModel):
    indexed: int
    catalog_size: int


class EuvsDisinfoSyncStatus(ApiModel):
    enabled: bool
    running: bool
    last_finished_at: Timestamp | None
    last_indexed: int
    last_skipped: int
    last_error: str | None
    available: int | None


class CorpusSyncStatus(ApiModel):
    running: bool
    last_finished_at: Timestamp | None
    available: int | None
    indexed: int
    skipped_duplicates: int
    skipped_outside_catalog: int
    failed: int
    last_error: str | None


class IncidentCatalogSummary(ApiModel):
    catalog_size: int
    euvsdisinfo: EuvsDisinfoSyncStatus | None = None


class IncidentMatch(ApiModel):
    incident_id: str
    source: str
    title: str
    summary: str
    url: str
    published_at: Timestamp | None
    score: float


class CampaignAlert(ApiModel):
    """Context only: never evidence and never a basis for a verdict (brief scenario I, AGENTS.md §4)."""

    category: Literal["possible_disinformation_campaign"]
    message: str
    matches: list[IncidentMatch]


class ExternalSourceStatus(ApiModel):
    name: str
    status: Literal["ok", "disabled", "skipped", "error"]
    results: int


class SearchResponse(ApiModel):
    results: list[Passage]
    corpus_version: str
    context_xml: str
    expanded_queries: ExpandedQueries
    elapsed_ms: int
    external_sources: list[ExternalSourceStatus]
    campaign_alert: CampaignAlert | None = None


class SourceAuditEntry(ApiModel):
    document_id: str
    title: str
    publisher: str
    domain: str
    url: str
    source_type: SourceType
    license: str | None
    published_at: Timestamp | None
    fetched_at: Timestamp
    active_chunks: int
    in_catalog: bool


DependencyStatus = Literal["ok", "unavailable"]


class HealthResponse(ApiModel):
    status: Literal["ok", "degraded"]
    corpus_version: str | None
    database: DependencyStatus
    qdrant: DependencyStatus
    incident_catalog: DependencyStatus


class DeletionReport(ApiModel):
    document_id: str
    chunks_deleted: int


class EvictionReport(ApiModel):
    active_before: int
    evicted: int
