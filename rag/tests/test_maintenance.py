from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app import maintenance
from app.config import settings
from app.maintenance import (
    JOB_CORPUS_REFRESH,
    JOB_EUVSDISINFO,
    JOB_EVICTION,
    JOB_FEEDS_REFRESH,
    JOB_LAW_REFRESH,
    JOB_ODYSEUSZ_REFRESH,
    JOB_OPTIMIZE,
    JOB_RECONCILE,
    register_maintenance_jobs,
)


class FakeStore:
    async def optimize(self) -> None:
        return None


class FakeEuvsDisinfo:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled


def job_ids(scheduler: AsyncIOScheduler) -> set[str]:
    return {job.id for job in scheduler.get_jobs()}


def test_official_sources_are_refreshed_on_a_schedule(monkeypatch):
    monkeypatch.setattr(maintenance, "seed_urls", lambda: ["https://www.gov.pl/web/premier/x"])
    scheduler = AsyncIOScheduler()
    register_maintenance_jobs(scheduler, FakeStore(), object(), FakeStore(), FakeEuvsDisinfo(enabled=False))

    assert job_ids(scheduler) == {
        JOB_EVICTION,
        JOB_RECONCILE,
        JOB_OPTIMIZE,
        JOB_CORPUS_REFRESH,
        JOB_LAW_REFRESH,
        JOB_FEEDS_REFRESH,
        JOB_ODYSEUSZ_REFRESH,
    }
    refresh = scheduler.get_job(JOB_CORPUS_REFRESH)
    assert refresh.args[0] == ["https://www.gov.pl/web/premier/x"]
    assert str(refresh.trigger.fields[5]) == str(settings.corpus_refresh_cron_hour)
    law = scheduler.get_job(JOB_LAW_REFRESH)
    assert law.args[2:] == (settings.law_refresh_max_chars, settings.law_part_max_chars)
    assert str(law.trigger.fields[4]) == settings.law_refresh_cron_day_of_week
    odyseusz = scheduler.get_job(JOB_ODYSEUSZ_REFRESH)
    assert odyseusz.trigger.interval.total_seconds() == settings.odyseusz_refresh_interval_minutes * 60
    # The first full import waits odyseusz_first_run_delay_minutes, so it does not slow the first checks after start.
    assert odyseusz.next_run_time is not None
    delay = odyseusz.next_run_time - datetime.now(UTC)
    assert timedelta(minutes=settings.odyseusz_first_run_delay_minutes - 1) < delay
    assert delay <= timedelta(minutes=settings.odyseusz_first_run_delay_minutes)


def test_odyseusz_refresh_follows_its_switch(monkeypatch):
    monkeypatch.setattr(maintenance, "seed_urls", lambda: [])
    monkeypatch.setattr(settings, "odyseusz_enabled", False)
    scheduler = AsyncIOScheduler()
    register_maintenance_jobs(scheduler, FakeStore(), object(), FakeStore(), FakeEuvsDisinfo(enabled=False))
    assert JOB_ODYSEUSZ_REFRESH not in job_ids(scheduler)


def test_refresh_and_euvsdisinfo_jobs_follow_their_switches(monkeypatch):
    monkeypatch.setattr(maintenance, "seed_urls", lambda: [])
    monkeypatch.setattr(settings, "corpus_refresh_enabled", False)
    scheduler = AsyncIOScheduler()
    register_maintenance_jobs(scheduler, FakeStore(), object(), FakeStore(), FakeEuvsDisinfo(enabled=True))

    ids = job_ids(scheduler)
    assert JOB_CORPUS_REFRESH not in ids and JOB_LAW_REFRESH not in ids
    assert JOB_EUVSDISINFO in ids
