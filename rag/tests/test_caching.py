import pytest

from app import caching
from app.caching import TtlCache


@pytest.fixture
def clock(monkeypatch):
    """Frozen monotonic clock the tests advance explicitly."""
    now = [1000.0]
    monkeypatch.setattr(caching.time, "monotonic", lambda: now[0])
    return now


def test_entry_expires_after_ttl(clock):
    cache = TtlCache(ttl_seconds=10, max_entries=5)
    cache.put("a", 1)
    clock[0] += 9
    assert cache.get("a") == 1
    clock[0] += 2
    assert cache.get("a") is None


def test_lru_eviction_removes_the_least_recently_used_entry(clock):
    cache = TtlCache(ttl_seconds=100, max_entries=2)
    cache.put("a", 1)
    cache.put("b", 2)
    assert cache.get("a") == 1  # a becomes the most recently used
    clock[0] += 1
    cache.put("c", 3)
    assert cache.get("b") is None
    assert cache.get("a") == 1
    assert cache.get("c") == 3


def test_expired_entries_are_purged_before_lru_eviction(clock):
    cache = TtlCache(ttl_seconds=10, max_entries=2)
    cache.put("a", 1)
    clock[0] += 20
    cache.put("b", 2)
    cache.put("c", 3)  # a expired, so b survives the insert instead of being evicted
    assert cache.get("a") is None
    assert cache.get("b") == 2
    assert cache.get("c") == 3
