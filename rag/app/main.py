import logging
import secrets
from contextlib import asynccontextmanager
from typing import Annotated
from urllib.parse import urlparse

import asyncpg
import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from app import db
from app.catalog import SourceOutsideCatalogError, load_catalog, resolve_entry
from app.config import settings
from app.corpus_sync import fetch_corpus, fetch_state, seed_urls, sync_corpus
from app.corpus_sync import sync_state as corpus_sync_state
from app.embeddings import EmbeddingModels
from app.euvsdisinfo import EuvsDisinfoClient, sync_cases, sync_state
from app.eviction import run_eviction
from app.factcheck import FactCheckClient
from app.fetcher import FetchError, fetch_page
from app.incidents import incident_point_id, index_incidents
from app.ingest import DuplicateDocumentError, ingest_document
from app.models import (
    CorpusFetchRequest,
    CorpusSyncStatus,
    DeletionReport,
    EuvsDisinfoSyncStatus,
    EvictionReport,
    ExternalSourceInfo,
    FetchRequest,
    FetchResponse,
    HealthResponse,
    IncidentCatalogSummary,
    IncidentIngestRequest,
    IncidentIngestResult,
    IngestRequest,
    IngestResult,
    SearchRequest,
    SearchResponse,
    SourceAuditEntry,
    SourceCatalog,
)
from app.search import FACTCHECK_SOURCE_TYPE, search_passages
from app.vector_store import VectorStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

INDEX_UNAVAILABLE_CODE = "index_unavailable"
INDEX_UNAVAILABLE_MESSAGE = "Wyszukiwanie źródeł jest chwilowo niedostępne. Spróbuj ponownie za chwilę."
DOCUMENT_NOT_FOUND_MESSAGE = "Nie znaleziono aktywnego dokumentu o tym identyfikatorze."
ADMIN_DISABLED_MESSAGE = "Operacje administracyjne są wyłączone: brak RAG_ADMIN_TOKEN."
ADMIN_UNAUTHORIZED_MESSAGE = "Brak lub błędny token administracyjny."
HTTP_SERVICE_UNAVAILABLE = 503
HTTP_NOT_FOUND = 404
HTTP_UNAUTHORIZED = 401
HTTP_FORBIDDEN = 403
HTTP_ACCEPTED = 202
HTTP_CONFLICT = 409
HTTP_UNPROCESSABLE = 422
DUPLICATE_MESSAGE = "Dokument {document_id} ma tę samą treść co {duplicate_of}. Nie wgrano."
FETCH_FAILED_MESSAGE = "Nie udało się pobrać strony: {reason}."
NEAR_DUPLICATE_MESSAGE = "Dokument {document_id} ma niemal tę samą treść co {duplicate_of} (parafraza). Nie wgrano."
EUVSDISINFO_DISABLED_MESSAGE = "Import EUvsDisinfo jest wyłączony: brak EUVSDISINFO_TOKEN."


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()
    store = VectorStore()
    await store.ensure_collection()
    app.state.store = store
    app.state.models = EmbeddingModels()
    incidents = VectorStore(settings.incident_collection_name)
    await incidents.ensure_collection()
    app.state.incidents = incidents
    logger.info("Disinformation incident catalog: %d entries", await incidents.count())
    euvsdisinfo = EuvsDisinfoClient()
    app.state.euvsdisinfo = euvsdisinfo
    logger.info("EUvsDisinfo import %s", "enabled" if euvsdisinfo.enabled else "disabled (no EUVSDISINFO_TOKEN)")
    factcheck = FactCheckClient()
    app.state.factcheck = factcheck
    logger.info("Google Fact Check source %s", "enabled" if factcheck.enabled else "disabled (no FACTCHECK_API_KEY)")

    scheduler = AsyncIOScheduler()
    scheduler.add_job(run_eviction, "cron", hour=settings.eviction_cron_hour, args=[store])
    scheduler.add_job(store.optimize, "cron", hour=settings.optimize_cron_hour)
    if euvsdisinfo.enabled:
        scheduler.add_job(
            sync_cases,
            "cron",
            hour=settings.euvsdisinfo_sync_cron_hour,
            args=[euvsdisinfo, app.state.models, incidents, settings.euvsdisinfo_daily_sync_cases],
        )
    scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        await factcheck.close()
        await euvsdisinfo.close()
        await incidents.close()
        await store.close()
        await db.close()


app = FastAPI(title="Prawdowid RAG", lifespan=lifespan)


@app.exception_handler(asyncpg.PostgresError)
@app.exception_handler(UnexpectedResponse)
@app.exception_handler(ResponseHandlingException)
@app.exception_handler(OSError)
@app.exception_handler(Exception)
async def index_error_handler(request: Request, error: Exception) -> JSONResponse:
    """Any failure behind the API is reported as the contract's index_unavailable, never as an empty result."""
    logger.error("Request failed on %s", request.url.path, exc_info=error)
    return JSONResponse(
        status_code=HTTP_SERVICE_UNAVAILABLE,
        content={"error": {"code": INDEX_UNAVAILABLE_CODE, "message": INDEX_UNAVAILABLE_MESSAGE}},
    )


async def require_admin(x_admin_token: Annotated[str | None, Header()] = None) -> None:
    if not settings.admin_token:
        raise HTTPException(status_code=HTTP_FORBIDDEN, detail=ADMIN_DISABLED_MESSAGE)
    if x_admin_token is None or not secrets.compare_digest(x_admin_token, settings.admin_token):
        raise HTTPException(status_code=HTTP_UNAUTHORIZED, detail=ADMIN_UNAUTHORIZED_MESSAGE)


AdminOnly = [Depends(require_admin)]
AUDIT_FIELDS = (
    "document_id",
    "title",
    "publisher",
    "url",
    "source_type",
    "license",
    "published_at",
    "fetched_at",
    "active_chunks",
)


async def _dependency_status(probe) -> tuple[str, object]:
    try:
        return "ok", await probe
    except Exception as error:
        logger.warning("Health probe failed: %s", type(error).__name__)
        return "unavailable", None


@app.get("/health", response_model=HealthResponse, responses={HTTP_SERVICE_UNAVAILABLE: {"model": HealthResponse}})
async def health(response: Response) -> HealthResponse:
    """Checks every dependency a search needs; 503 + degraded lets backend and compose see a half-dead rag."""
    database, corpus_version = await _dependency_status(db.corpus_version())
    qdrant, _ = await _dependency_status(app.state.store.count())
    catalog, _ = await _dependency_status(app.state.incidents.count())
    status = "ok" if database == qdrant == catalog == "ok" else "degraded"
    if status == "degraded":
        response.status_code = HTTP_SERVICE_UNAVAILABLE
    return HealthResponse(
        status=status, corpus_version=corpus_version, database=database, qdrant=qdrant, incident_catalog=catalog
    )


@app.post("/search", response_model=SearchResponse)
async def search(request: SearchRequest, background_tasks: BackgroundTasks) -> SearchResponse:
    response = await search_passages(
        request, app.state.models, app.state.store, app.state.factcheck, app.state.incidents
    )
    corpus_chunk_ids = [item.chunk_id for item in response.results if item.source_type != FACTCHECK_SOURCE_TYPE]
    if corpus_chunk_ids:
        background_tasks.add_task(db.register_reads, corpus_chunk_ids)
    return response


@app.post("/ingest", response_model=list[IngestResult], dependencies=AdminOnly)
async def ingest(request: IngestRequest) -> list[IngestResult]:
    """Documents are processed in order; on 422/409 the earlier ones stay indexed and the detail names the culprit."""
    results: list[IngestResult] = []
    for document in request.documents:
        try:
            results.append(await ingest_document(document, app.state.models, app.state.store))
        except SourceOutsideCatalogError as error:
            raise HTTPException(status_code=HTTP_UNPROCESSABLE, detail=str(error)) from error
        except DuplicateDocumentError as error:
            message = NEAR_DUPLICATE_MESSAGE if error.near else DUPLICATE_MESSAGE
            raise HTTPException(
                status_code=HTTP_CONFLICT,
                detail=message.format(document_id=error.document_id, duplicate_of=error.duplicate_of),
            ) from error
    return results


@app.post("/fetch", response_model=FetchResponse)
async def fetch_url(request: FetchRequest) -> FetchResponse:
    """Page text for agent/ when the user submits a URL; nothing is stored, the same parser as for the corpus."""
    try:
        async with httpx.AsyncClient(timeout=settings.corpus_fetch_timeout_seconds, follow_redirects=True) as client:
            page = await fetch_page(client, str(request.url))
    except FetchError as error:
        raise HTTPException(status_code=HTTP_UNPROCESSABLE, detail=FETCH_FAILED_MESSAGE.format(reason=error)) from error
    truncated = len(page.text) > settings.fetch_max_text_chars
    return FetchResponse(
        url=page.url, title=page.title, text=page.text[: settings.fetch_max_text_chars], truncated=truncated
    )


@app.get("/sources/external", response_model=list[ExternalSourceInfo])
async def sources_external() -> list[ExternalSourceInfo]:
    """Live services and imported registers used beside the corpus, with what they get and their current state."""
    runtime = {
        "google_factcheck": {"enabled": app.state.factcheck.enabled},
        "euvsdisinfo": {
            "enabled": app.state.euvsdisinfo.enabled,
            "catalogSize": await app.state.incidents.count(),
            "lastSyncFinishedAt": sync_state.last_finished_at.isoformat() if sync_state.last_finished_at else None,
            "lastSyncIndexed": sync_state.last_indexed,
        },
    }
    return [
        ExternalSourceInfo(**entry.model_dump(), **runtime.get(entry.name, {"enabled": False}))
        for entry in load_catalog().external
    ]


@app.get("/sources/catalog", response_model=SourceCatalog)
async def sources_catalog() -> SourceCatalog:
    """Trusted-source catalog with qualification rules: what gets in, with which tier, and when it is excluded."""
    return load_catalog()


@app.get("/sources", response_model=list[SourceAuditEntry])
async def sources() -> list[SourceAuditEntry]:
    return [
        SourceAuditEntry(
            **{field: row[field] for field in AUDIT_FIELDS},
            domain=urlparse(row["url"]).hostname or "",
            in_catalog=resolve_entry(row["url"]) is not None,
        )
        for row in await db.list_sources()
    ]


@app.delete("/sources/{document_id}", response_model=DeletionReport, dependencies=AdminOnly)
async def delete_document(document_id: str) -> DeletionReport:
    chunk_ids = await db.active_chunk_ids_for_document(document_id)
    if not chunk_ids:
        raise HTTPException(status_code=HTTP_NOT_FOUND, detail=DOCUMENT_NOT_FOUND_MESSAGE)
    await app.state.store.delete(chunk_ids)
    await db.mark_chunks_deleted(chunk_ids)
    logger.info("document %s deleted on request (%d chunks)", document_id, len(chunk_ids))
    return DeletionReport(document_id=document_id, chunks_deleted=len(chunk_ids))


@app.post("/incidents", response_model=IncidentIngestResult, dependencies=AdminOnly)
async def ingest_incidents(request: IncidentIngestRequest) -> IncidentIngestResult:
    indexed = await index_incidents(request.incidents, app.state.models, app.state.incidents)
    return IncidentIngestResult(indexed=indexed, catalog_size=await app.state.incidents.count())


def _euvsdisinfo_status() -> EuvsDisinfoSyncStatus:
    return EuvsDisinfoSyncStatus(
        enabled=app.state.euvsdisinfo.enabled,
        running=sync_state.running,
        last_finished_at=sync_state.last_finished_at,
        last_indexed=sync_state.last_indexed,
        last_skipped=sync_state.last_skipped,
        last_error=sync_state.last_error,
        available=sync_state.available,
    )


@app.get("/incidents", response_model=IncidentCatalogSummary)
async def incident_catalog() -> IncidentCatalogSummary:
    return IncidentCatalogSummary(catalog_size=await app.state.incidents.count(), euvsdisinfo=_euvsdisinfo_status())


@app.post(
    "/admin/incidents/sync",
    response_model=EuvsDisinfoSyncStatus,
    status_code=HTTP_ACCEPTED,
    dependencies=AdminOnly,
)
async def sync_euvsdisinfo(
    background_tasks: BackgroundTasks,
    max_cases: Annotated[
        int, Query(alias="maxCases", ge=1, le=settings.euvsdisinfo_sync_max_cases)
    ] = settings.euvsdisinfo_sync_default_cases,
) -> EuvsDisinfoSyncStatus:
    """Starts importing the newest `maxCases` EUvsDisinfo cases in the background; progress is in GET /incidents."""
    if not app.state.euvsdisinfo.enabled:
        raise HTTPException(status_code=HTTP_FORBIDDEN, detail=EUVSDISINFO_DISABLED_MESSAGE)
    if not sync_state.running:
        background_tasks.add_task(sync_cases, app.state.euvsdisinfo, app.state.models, app.state.incidents, max_cases)
    return _euvsdisinfo_status()


@app.delete("/incidents/{source}/{incident_id}", response_model=IncidentCatalogSummary, dependencies=AdminOnly)
async def delete_incident(source: str, incident_id: str) -> IncidentCatalogSummary:
    await app.state.incidents.delete([incident_point_id(source, incident_id)])
    logger.info("incident %s/%s deleted on request", source, incident_id)
    return IncidentCatalogSummary(catalog_size=await app.state.incidents.count())


def _corpus_status(state) -> CorpusSyncStatus:
    return CorpusSyncStatus(
        running=state.running,
        last_finished_at=state.last_finished_at,
        available=state.available,
        indexed=state.indexed,
        skipped_duplicates=state.skipped_duplicates,
        skipped_outside_catalog=state.skipped_outside_catalog,
        failed=state.failed,
        last_error=state.last_error,
    )


def _corpus_sync_status() -> CorpusSyncStatus:
    return _corpus_status(corpus_sync_state)


@app.get("/corpus/fetch", response_model=CorpusSyncStatus)
async def corpus_fetch_status() -> CorpusSyncStatus:
    return _corpus_status(fetch_state)


@app.post("/admin/corpus/fetch", response_model=CorpusSyncStatus, status_code=HTTP_ACCEPTED, dependencies=AdminOnly)
async def start_corpus_fetch(
    background_tasks: BackgroundTasks, request: CorpusFetchRequest | None = None
) -> CorpusSyncStatus:
    """Fetches public pages (given URLs, or the seed list from catalog domains) into the corpus in the background."""
    urls = [str(url) for url in request.urls] if request and request.urls else seed_urls()
    if not fetch_state.running:
        background_tasks.add_task(fetch_corpus, urls, app.state.models, app.state.store)
    return _corpus_status(fetch_state)


@app.get("/corpus/sync", response_model=CorpusSyncStatus)
async def corpus_sync_status() -> CorpusSyncStatus:
    return _corpus_sync_status()


@app.post("/admin/corpus/sync", response_model=CorpusSyncStatus, status_code=HTTP_ACCEPTED, dependencies=AdminOnly)
async def start_corpus_sync(
    background_tasks: BackgroundTasks,
    max_documents: Annotated[
        int, Query(alias="maxDocuments", ge=1, le=settings.corpus_sync_max_documents)
    ] = settings.corpus_sync_max_documents,
) -> CorpusSyncStatus:
    """Imports the scraper's pages from the shared database in the background; GET /corpus/sync shows progress."""
    if not corpus_sync_state.running:
        background_tasks.add_task(sync_corpus, app.state.models, app.state.store, max_documents)
    return _corpus_sync_status()


@app.post("/admin/eviction", response_model=EvictionReport, dependencies=AdminOnly)
async def eviction() -> EvictionReport:
    return await run_eviction(app.state.store)
