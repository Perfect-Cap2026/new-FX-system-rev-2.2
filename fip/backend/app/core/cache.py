"""Cache with Redis when REDIS_URL is set, in-process TTL dict otherwise."""
import logging
import pickle
import threading
import time
from typing import Any, Callable

from app.core.config import get_settings
from app.core.logging import CACHE

log = logging.getLogger(__name__)


class _MemoryCache:
    def __init__(self, max_items: int = 2000):
        self._d: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()
        self._max = max_items

    def get(self, key: str):
        with self._lock:
            item = self._d.get(key)
            if not item:
                return None
            exp, val = item
            if exp < time.time():
                self._d.pop(key, None)
                return None
            return val

    def set(self, key: str, val: Any, ttl: int):
        with self._lock:
            if len(self._d) >= self._max:
                self._d.pop(next(iter(self._d)))
            self._d[key] = (time.time() + ttl, val)


class _RedisCache:
    def __init__(self, url: str):
        import redis

        self._r = redis.Redis.from_url(url)
        self._r.ping()

    def get(self, key: str):
        raw = self._r.get(f"fip:{key}")
        return pickle.loads(raw) if raw else None  # only our own process writes these keys

    def set(self, key: str, val: Any, ttl: int):
        self._r.setex(f"fip:{key}", ttl, pickle.dumps(val))


def _build():
    url = get_settings().redis_url
    if url:
        try:
            return _RedisCache(url)
        except Exception as e:  # pragma: no cover
            log.warning(f"Redis unavailable ({e}); using in-memory cache")
    return _MemoryCache()


cache = _build()


def cached(key: str, ttl: int, fn: Callable[[], Any]) -> Any:
    val = cache.get(key)
    if val is not None:
        CACHE.labels("hit").inc()
        return val
    CACHE.labels("miss").inc()
    val = fn()
    empty = val is None or getattr(val, "empty", False) or (isinstance(val, (list, dict)) and not val)
    if not empty:  # never cache failures/empties — a provider hiccup shouldn't stick for the TTL
        cache.set(key, val, ttl)
    return val
