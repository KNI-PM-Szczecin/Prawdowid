from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import settings
from app.corpus_sync import fetch_corpus, seed_urls
from app.embeddings import EmbeddingModels
from app.euvsdisinfo import EuvsDisinfoClient, sync_cases
from app.eviction import run_eviction
from app.feeds import refresh_feeds
from app.law_import import import_law
from app.odyseusz import refresh_odyseusz
from app.reconcile import reconcile_vectors
from app.vector_store import VectorStore

JOB_EVICTION = "eviction"
JOB_RECONCILE = "reconcile"
JOB_OPTIMIZE = "optimize"
JOB_EUVSDISINFO = "euvsdisinfo_sync"
JOB_CORPUS_REFRESH = "corpus_refresh"
JOB_LAW_REFRESH = "law_refresh"
JOB_FEEDS_REFRESH = "feeds_refresh"
JOB_ODYSEUSZ_REFRESH = "odyseusz_refresh"


def register_maintenance_jobs(
    scheduler: AsyncIOScheduler,
    store: VectorStore,
    models: EmbeddingModels,
    incidents: VectorStore,
    euvsdisinfo: EuvsDisinfoClient,
) -> None:
    """
    Nightly housekeeping and the refresh schedule for official sources. Every job is also reachable by hand through
    the admin endpoints; the schedule only makes sure nobody has to remember. Jobs never overlap with a manual run
    of the same import: each import keeps its own lock and skips when busy.
    """
    scheduler.add_job(run_eviction, "cron", id=JOB_EVICTION, hour=settings.eviction_cron_hour, args=[store])
    # Stale points first, so the optimizer that follows compacts a collection without them.
    scheduler.add_job(reconcile_vectors, "cron", id=JOB_RECONCILE, hour=settings.optimize_cron_hour, args=[store])
    scheduler.add_job(
        store.optimize,
        "cron",
        id=JOB_OPTIMIZE,
        hour=settings.optimize_cron_hour,
        minute=settings.optimize_cron_minute,
    )
    if euvsdisinfo.enabled:
        scheduler.add_job(
            sync_cases,
            "cron",
            id=JOB_EUVSDISINFO,
            hour=settings.euvsdisinfo_sync_cron_hour,
            args=[euvsdisinfo, models, incidents, settings.euvsdisinfo_daily_sync_cases],
        )
    if settings.feeds_refresh_enabled:
        scheduler.add_job(
            refresh_feeds,
            "interval",
            id=JOB_FEEDS_REFRESH,
            minutes=settings.feeds_refresh_interval_minutes,
            args=[models, store],
        )
    if settings.odyseusz_enabled:
        # First run right after start, in the background: travel notices change daily and the corpus may be empty.
        scheduler.add_job(
            refresh_odyseusz,
            "interval",
            id=JOB_ODYSEUSZ_REFRESH,
            minutes=settings.odyseusz_refresh_interval_minutes,
            next_run_time=datetime.now(UTC),
            args=[models, store],
        )
    if settings.corpus_refresh_enabled:
        # A page fetched again with the same text replaces its own chunks; a changed page replaces them with the
        # new text and date, so the corpus follows the publisher (brief: prefer current data).
        scheduler.add_job(
            fetch_corpus,
            "cron",
            id=JOB_CORPUS_REFRESH,
            hour=settings.corpus_refresh_cron_hour,
            args=[seed_urls(), models, store],
        )
        # A newer consolidated text of an act (new Dz.U. position) replaces the old document law:<id>.
        scheduler.add_job(
            import_law,
            "cron",
            id=JOB_LAW_REFRESH,
            day_of_week=settings.law_refresh_cron_day_of_week,
            hour=settings.law_refresh_cron_hour,
            args=[models, store, settings.law_refresh_max_chars, settings.law_part_max_chars],
        )
