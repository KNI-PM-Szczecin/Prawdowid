import logging
from contextlib import asynccontextmanager

import asyncpg
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from app import db
from app.config import settings
from app.embeddings import EmbeddingModels
from app.eviction import run_eviction
from app.ingest import ingest_document
from app.models import (
    DeletionReport,
    EvictionReport,
    IngestRequest,
    IngestResult,
    SearchRequest,
    SearchResponse,
    SourceAuditEntry,
)
from app.search import search_evidence
from app.vector_store import VectorStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

TECHNICAL_ERROR_STATUS = "technical_error"
TECHNICAL_ERROR_MESSAGE = "Wyszukiwanie źródeł jest chwilowo niedostępne. Spróbuj ponownie za chwilę."
HTTP_SERVICE_UNAVAILABLE = 503
HTTP_NOT_FOUND = 404


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()
    store = VectorStore()
    await store.ensure_collection()
    app.state.store = store
    app.state.models = EmbeddingModels()

    scheduler = AsyncIOScheduler()
    scheduler.add_job(run_eviction, "cron", hour=settings.eviction_cron_hour, args=[store])
    scheduler.add_job(store.optimize, "cron", hour=settings.optimize_cron_hour)
    scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        await store.close()
        await db.close()


app = FastAPI(title="Prawdowid RAG", lifespan=lifespan)


@app.exception_handler(asyncpg.PostgresError)
@app.exception_handler(UnexpectedResponse)
@app.exception_handler(ResponseHandlingException)
@app.exception_handler(OSError)
async def storage_error_handler(request: Request, error: Exception) -> JSONResponse:
    logger.error("Storage failure on %s", request.url.path, exc_info=error)
    return JSONResponse(
        status_code=HTTP_SERVICE_UNAVAILABLE,
        content={"status": TECHNICAL_ERROR_STATUS, "message": TECHNICAL_ERROR_MESSAGE},
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/search", response_model=SearchResponse)
async def search(request: SearchRequest, background_tasks: BackgroundTasks) -> SearchResponse:
    response = await search_evidence(request.claim, request.top_k, app.state.models, app.state.store)
    if response.evidence:
        background_tasks.add_task(db.register_reads, [item.chunk_id for item in response.evidence])
    return response


@app.post("/ingest", response_model=list[IngestResult])
async def ingest(request: IngestRequest) -> list[IngestResult]:
    return [await ingest_document(document, app.state.models, app.state.store) for document in request.documents]


@app.get("/sources", response_model=list[SourceAuditEntry])
async def sources() -> list[SourceAuditEntry]:
    return [SourceAuditEntry(**dict(row)) for row in await db.list_sources()]


@app.delete("/sources/{source_id}", response_model=DeletionReport)
async def delete_source(source_id: str) -> DeletionReport:
    chunk_ids = await db.active_chunk_ids_for_source(source_id)
    if not chunk_ids:
        raise HTTPException(status_code=HTTP_NOT_FOUND, detail="Nie znaleziono aktywnego źródła o tym identyfikatorze.")
    await app.state.store.delete(chunk_ids)
    await db.mark_chunks_deleted(chunk_ids)
    logger.info("source %s deleted on request (%d chunks)", source_id, len(chunk_ids))
    return DeletionReport(source_id=source_id, chunks_deleted=len(chunk_ids))


@app.post("/admin/eviction", response_model=EvictionReport)
async def eviction() -> EvictionReport:
    return await run_eviction(app.state.store)
