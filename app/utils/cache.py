"""
Caching utilities for low-latency performance.

Provides TTL-based and LRU caching for embeddings,
schema metadata, and other frequently accessed data.
"""

import time
import threading
from typing import Any, Optional, Callable
from functools import wraps
import hashlib
import logging

logger = logging.getLogger(__name__)


class TTLCache:
    """Thread-safe cache with time-to-live expiration."""

    def __init__(self, ttl_seconds: int = 300, max_size: int = 1000):
        self._cache: dict = {}
        self._timestamps: dict = {}
        self._ttl = ttl_seconds
        self._max_size = max_size
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        """Get a value from cache. Returns None if expired or missing."""
        with self._lock:
            if key in self._cache:
                if time.time() - self._timestamps[key] < self._ttl:
                    self._hits += 1
                    return self._cache[key]
                else:
                    # Expired
                    del self._cache[key]
                    del self._timestamps[key]
            self._misses += 1
            return None

    def set(self, key: str, value: Any):
        """Set a value in cache."""
        with self._lock:
            # Evict oldest if at capacity
            if len(self._cache) >= self._max_size and key not in self._cache:
                oldest_key = min(self._timestamps, key=self._timestamps.get)
                del self._cache[oldest_key]
                del self._timestamps[oldest_key]

            self._cache[key] = value
            self._timestamps[key] = time.time()

    def invalidate(self, key: str):
        """Remove a specific key from cache."""
        with self._lock:
            self._cache.pop(key, None)
            self._timestamps.pop(key, None)

    def clear(self):
        """Clear the entire cache."""
        with self._lock:
            self._cache.clear()
            self._timestamps.clear()
            self._hits = 0
            self._misses = 0

    @property
    def stats(self) -> dict:
        """Return cache hit/miss statistics."""
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / total, 3) if total > 0 else 0,
            "size": len(self._cache),
        }


def cache_key(*args, **kwargs) -> str:
    """Generate a deterministic cache key from arguments."""
    key_parts = [str(a) for a in args] + [f"{k}={v}" for k, v in sorted(kwargs.items())]
    raw = "|".join(key_parts)
    return hashlib.md5(raw.encode()).hexdigest()


# ── Global cache instances ───────────────────────────────────────
schema_cache = TTLCache(ttl_seconds=600, max_size=100)   # 10 min TTL for schema
embedding_cache = TTLCache(ttl_seconds=3600, max_size=5000)  # 1 hour for embeddings
