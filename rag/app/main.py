import logging
import secrets
from contextlib import asynccontextmanager
from typing import Annotated
from urllib.parse import urlparse

import asyncpg
import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import JSONResponse
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from app import db
from app.catalog import SourceOutsideCatalogError, load_catalog, resolve_entry
from app.config import settings
from app.corpus_sync import fetch_corpus, fetch_state, prune_corpus, seed_urls, sync_corpus
from app.corpus_sync import sync_state as corpus_sync_state
from app.embeddings import EmbeddingModels
from app.euvsdisinfo import EuvsDisinfoClient, sync_cases, sync_state
from app.eviction import run_eviction
from app.factcheck import FactCheckClient
from app.fetcher import FetchError, fetch_page
from app.gov_search import GovSearchClient
from app.gov_search import wanted as gov_search_wanted
from app.incidents import ensure_seed_incidents, incident_point_id, index_incidents
from app.ingest import DuplicateDocumentError, delete_document_chunks, ingest_document
from app.law_import import import_law, law_state
from app.maintenance import register_maintenance_jobs
from app.material import match_material
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
    MaterialMatchRequest,
    MaterialMatchResponse,
    OcrResponse,
    PruneReport,
    ReconcileReport,
    ReportMatchRequest,
    ReportMatchResponse,
    SearchRequest,
    SearchResponse,
    SourceAuditEntry,
    SourceCatalog,
)
from app.ocr import OcrError, OcrUnavailableError, read_image
from app.reconcile import reconcile_vectors
from app.reports import REPORTS_COLLECTION_NAME, match_report
from app.search import FACTCHECK_SOURCE_TYPE, search_passages
from app.seed import ensure_seed_corpus
from app.vector_store import VectorStore
from app.warmup import warm_up

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
OCR_FAILED_MESSAGE = "Nie udało się odczytać obrazu: {reason}."
OCR_UNAVAILABLE_MESSAGE = "Odczyt tekstu z obrazu jest chwilowo niedostępny."
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
    reports = VectorStore(REPORTS_COLLECTION_NAME)
    await reports.ensure_collection()
    app.state.reports = reports
    logger.info("Disinformation incident catalog: %d entries", await incidents.count())
    euvsdisinfo = EuvsDisinfoClient()
    app.state.euvsdisinfo = euvsdisinfo
    logger.info("EUvsDisinfo import %s", "enabled" if euvsdisinfo.enabled else "disabled (no EUVSDISINFO_TOKEN)")
    factcheck = FactCheckClient()
    app.state.factcheck = factcheck
    gov_search = GovSearchClient()
    app.state.gov_search = gov_search
    logger.info("gov.pl gap filling %s", "enabled" if gov_search.enabled else "disabled")
    logger.info("Google Fact Check source %s", "enabled" if factcheck.enabled else "disabled (no FACTCHECK_API_KEY)")

    # Before the scheduler and before uvicorn accepts requests: the first citizen search must not pay for cold models.
    await warm_up(app.state.models, store)

    if settings.seed_corpus_enabled:
        seed_report = await ensure_seed_corpus(app.state.models, store)
        logger.info(
            "Seed corpus: %d indexed (%d without vectors here), %d already present, %d duplicates, %d failed",
            seed_report.indexed,
            seed_report.missing_vectors,
            seed_report.already_present,
            seed_report.skipped_duplicates,
            seed_report.failed,
        )
    if settings.seed_incidents_enabled:
        try:
            # Upserted at every start, not only when the catalog is empty: an EUvsDisinfo import can run
            # first and then the demo-critical cases would never arrive (they fall outside newest-N).
            seeded = await ensure_seed_incidents(app.state.models, incidents)
            logger.info("Seed incident catalog ensured: %d entries", seeded)
        except Exception:
            logger.exception("Seeding the incident catalog failed; search continues without it")

    scheduler = AsyncIOScheduler()
    register_maintenance_jobs(scheduler, store, app.state.models, incidents, euvsdisinfo)
    scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        await factcheck.close()
        await gov_search.close()
        await euvsdisinfo.close()
        await incidents.close()
        await reports.close()
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


@app.post("/reports/match", response_model=ReportMatchResponse)
async def reports_match(request: ReportMatchRequest) -> ReportMatchResponse:
    """Groups an unresolved question with earlier similar ones for the moderator; called by the backend only."""
    case_id, matched, score = await match_report(request.claim, app.state.models, app.state.reports)
    return ReportMatchResponse(case_id=case_id, matched=matched, score=score)


@app.post("/search", response_model=SearchResponse)
async def search(request: SearchRequest, background_tasks: BackgroundTasks) -> SearchResponse:
    response = await search_passages(
        request, app.state.models, app.state.store, app.state.factcheck, app.state.incidents
    )
    if gov_search_wanted(request, len(response.results)):
        gap_fill = await app.state.gov_search.fill(request.query, app.state.models, app.state.store)
        if gap_fill.indexed:
            response = await search_passages(
                request, app.state.models, app.state.store, app.state.factcheck, app.state.incidents
            )
        response = response.model_copy(update={"external_sources": [*response.external_sources, gap_fill.as_status()]})
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
        # fetch_timeout_seconds, not the corpus one: agent/ gives rag 12 s, so a 15 s page would be a
        # guaranteed technical_error on agent's side before this endpoint ever answered. Redirects are
        # followed inside fetch_page, with a URL guard check on every target.
        async with httpx.AsyncClient(timeout=settings.fetch_timeout_seconds, follow_redirects=False) as client:
            page = await fetch_page(client, str(request.url))
    except FetchError as error:
        raise HTTPException(
            status_code=HTTP_UNPROCESSABLE,
            detail={"message": FETCH_FAILED_MESSAGE.format(reason=error), "code": error.code},
        ) from error
    truncated = len(page.text) > settings.fetch_max_text_chars
    return FetchResponse(
        url=page.url,
        title=page.title,
        text=page.text[: settings.fetch_max_text_chars],
        truncated=truncated,
        published_at=page.published_at,
    )


@app.post("/ocr", response_model=OcrResponse)
async def ocr(image: UploadFile) -> OcrResponse:
    """Text of a screenshot or photo for agent/ (brief scenario F); read locally, nothing is stored."""
    data = await image.read(settings.ocr_max_bytes + 1)
    try:
        result = await read_image(data)
    except OcrError as error:
        raise HTTPException(status_code=HTTP_UNPROCESSABLE, detail=OCR_FAILED_MESSAGE.format(reason=error)) from error
    except OcrUnavailableError as error:
        raise HTTPException(status_code=HTTP_SERVICE_UNAVAILABLE, detail=OCR_UNAVAILABLE_MESSAGE) from error
    return OcrResponse(text=result.text, confidence=result.confidence, dates=result.dates, engine=result.engine)


@app.post("/match", response_model=MaterialMatchResponse)
async def match(request: MaterialMatchRequest) -> MaterialMatchResponse:
    """Is the submitted page itself a known material (corpus document or incident link)? Context, never a verdict."""
    return await match_material(request, app.state.incidents)


@app.get("/sources/external", response_model=list[ExternalSourceInfo])
async def sources_external() -> list[ExternalSourceInfo]:
    """Live services and imported registers used beside the corpus, with what they get and their current state."""
    runtime = {
        "google_factcheck": {"enabled": app.state.factcheck.enabled},
        "gov_search": {"enabled": app.state.gov_search.enabled},
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
    chunks_deleted = await delete_document_chunks(document_id, app.state.store)
    if not chunks_deleted:
        raise HTTPException(status_code=HTTP_NOT_FOUND, detail=DOCUMENT_NOT_FOUND_MESSAGE)
    logger.info("document %s deleted on request (%d chunks)", document_id, chunks_deleted)
    return DeletionReport(document_id=document_id, chunks_deleted=chunks_deleted)


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
        already_present=state.already_present,
        skipped_duplicates=state.skipped_duplicates,
        skipped_excluded=state.skipped_excluded,
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


@app.post("/admin/corpus/prune", response_model=PruneReport, dependencies=AdminOnly)
async def prune(dry_run: Annotated[bool, Query(alias="dryRun")] = False) -> PruneReport:
    """
    Removes bulk-imported documents that app/data/corpus_rules.json excludes (listing pages, home pages, police
    news). With dryRun=true only lists what would go, so a rule change can be checked before it deletes anything.
    """
    return await prune_corpus(app.state.store, dry_run=dry_run)


@app.get("/corpus/law", response_model=CorpusSyncStatus)
async def corpus_law_status() -> CorpusSyncStatus:
    return _corpus_status(law_state)


@app.post("/admin/corpus/law", response_model=CorpusSyncStatus, status_code=HTTP_ACCEPTED, dependencies=AdminOnly)
async def start_law_import(
    background_tasks: BackgroundTasks,
    max_chars: Annotated[
        int, Query(alias="maxChars", ge=1, le=settings.law_import_max_chars)
    ] = settings.law_import_default_max_chars,
) -> CorpusSyncStatus:
    """Imports the acts from app/data/law_acts.json out of the scraper's Law table; GET /corpus/law shows progress."""
    if not law_state.running:
        background_tasks.add_task(import_law, app.state.models, app.state.store, max_chars, settings.law_part_max_chars)
    return _corpus_status(law_state)


@app.post("/admin/eviction", response_model=EvictionReport, dependencies=AdminOnly)
async def eviction() -> EvictionReport:
    return await run_eviction(app.state.store)


@app.post("/admin/corpus/reconcile", response_model=ReconcileReport, dependencies=AdminOnly)
async def reconcile(include_unknown: Annotated[bool, Query(alias="includeUnknown")] = False) -> ReconcileReport:
    """
    Deletes Qdrant points PostgreSQL marks as deleted. includeUnknown=true also drops points PostgreSQL has never
    seen; use it only when no import is running, because an import writes Qdrant before PostgreSQL.
    """
    return await reconcile_vectors(app.state.store, include_unknown=include_unknown)
