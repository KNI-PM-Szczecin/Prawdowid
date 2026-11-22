import time
from typing import TypeVar

Key = TypeVar("Key")
Value = TypeVar("Value")


class TtlCache[Key, Value]:
    """
    Fixed-capacity cache with per-entry TTL and LRU eviction. Entries expire lazily on access or insert;
    expired entries are purged when the cache is full instead of being kept until they are touched.
    Single-threaded use (one event loop) is assumed, like everywhere else in rag/.
    """

    def __init__(self, ttl_seconds: int, max_entries: int) -> None:
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._entries: dict[Key, tuple[float, Value]] = {}

    def get(self, key: Key) -> Value | None:
        entry = self._entries.get(key)
        if entry is None or entry[0] < time.monotonic():
            return None
        self._entries[key] = self._entries.pop(key)  # reinsert: LRU order is the dict insertion order
        return entry[1]

    def put(self, key: Key, value: Value) -> None:
        if len(self._entries) >= self._max_entries:
            self._purge_expired()
        if len(self._entries) >= self._max_entries:
            del self._entries[next(iter(self._entries))]  # least recently used
        self._entries[key] = (time.monotonic() + self._ttl_seconds, value)

    def _purge_expired(self) -> None:
        now = time.monotonic()
        expired = [key for key, (expires_at, _) in self._entries.items() if expires_at < now]
        for key in expired:
            del self._entries[key]

    def clear(self) -> None:
        self._entries.clear()
