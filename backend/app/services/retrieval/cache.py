"""Retrieval Cache: TTL in-memory store for serialized RetrievalContexts.

Key = hash(repository_id, query, mode, filters, limit, expansion_depth,
token_budget) so identical requests are served from cache while any change
(including an explicit filter) re-runs the pipeline. Thread-safe via a lock;
bounded size; per-cache hit/miss counters feed the metrics endpoint.
"""

import hashlib
import json
import threading
import time

from app.models.schemas.knowledge_chunks import ChunkFilters
from app.models.schemas.retrieval import SearchMode

DEFAULT_TTL_SECONDS = 300
DEFAULT_MAX_ENTRIES = 256


class RetrievalCache:
    def __init__(
        self,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        max_entries: int = DEFAULT_MAX_ENTRIES,
    ) -> None:
        self._ttl = ttl_seconds
        self._max = max_entries
        self._entries: dict[str, tuple[float, object]] = {}
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    @staticmethod
    def make_key(
        repository_id: str,
        query: str,
        mode: SearchMode,
        filters: ChunkFilters | None,
        limit: int,
        expansion_depth: int,
        token_budget: int | None,
    ) -> str:
        payload = {
            "repo": repository_id,
            "q": query.strip().lower(),
            "mode": mode.value,
            "filters": filters.model_dump() if filters else None,
            "limit": limit,
            "depth": expansion_depth,
            "budget": token_budget,
        }
        raw = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

    def get(self, key: str):
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                self._misses += 1
                return None
            expires_at, value = entry
            if time.monotonic() >= expires_at:
                del self._entries[key]
                self._misses += 1
                return None
            self._hits += 1
            return value

    def set(self, key: str, value) -> None:
        with self._lock:
            if len(self._entries) >= self._max and key not in self._entries:
                oldest = min(self._entries, key=lambda k: self._entries[k][0])
                del self._entries[oldest]
            self._entries[key] = (time.monotonic() + self._ttl, value)

    def stats(self) -> dict:
        with self._lock:
            total = self._hits + self._misses
            return {
                "size": len(self._entries),
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(self._hits / total, 4) if total else 0.0,
            }

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


def get_retrieval_cache() -> RetrievalCache:
    return RetrievalCache()
