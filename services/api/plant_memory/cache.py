"""Valkey-backed scoped cache and concurrency limits, with an in-process fallback.

Cache keys always include org, project, snapshot, permissions version, and the relevant
rule/tool versions, so a cached result can never be served across tenants or stale versions.
Release one uses exact-key reuse only (no semantic answer caching).
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from contextlib import contextmanager
from typing import Any, Iterator

from .config import get_settings


class _MemoryBackend:
    def __init__(self) -> None:
        self._data: dict[str, tuple[float, str]] = {}
        self._counters: dict[str, int] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> str | None:
        with self._lock:
            item = self._data.get(key)
            if not item:
                return None
            exp, val = item
            if exp < time.time():
                del self._data[key]
                return None
            return val

    def set(self, key: str, value: str, ttl: int) -> None:
        with self._lock:
            self._data[key] = (time.time() + ttl, value)

    def incr(self, key: str, ttl: int) -> int:
        with self._lock:
            self._counters[key] = self._counters.get(key, 0) + 1
            return self._counters[key]

    def decr(self, key: str) -> int:
        with self._lock:
            self._counters[key] = max(0, self._counters.get(key, 0) - 1)
            return self._counters[key]

    def ping(self) -> bool:
        return True


class _ValkeyBackend:
    def __init__(self, url: str) -> None:
        import redis

        self.r = redis.Redis.from_url(url, socket_timeout=1.0, socket_connect_timeout=1.0)

    def get(self, key: str) -> str | None:
        v = self.r.get(key)
        return v.decode() if v is not None else None

    def set(self, key: str, value: str, ttl: int) -> None:
        self.r.set(key, value, ex=ttl)

    def incr(self, key: str, ttl: int) -> int:
        pipe = self.r.pipeline()
        pipe.incr(key)
        pipe.expire(key, ttl)
        return int(pipe.execute()[0])

    def decr(self, key: str) -> int:
        v = int(self.r.decr(key))
        if v < 0:
            self.r.set(key, 0)
            return 0
        return v

    def ping(self) -> bool:
        return bool(self.r.ping())


_backend = None


def backend():
    global _backend
    if _backend is None:
        url = get_settings().valkey_url
        if url:
            try:
                b = _ValkeyBackend(url)
                b.ping()
                _backend = b
            except Exception:
                _backend = _MemoryBackend()
        else:
            _backend = _MemoryBackend()
    return _backend


def scoped_key(namespace: str, *, org_id, project_id, snapshot_id=None, permissions_version: int = 1, versions: dict[str, str] | None = None, **params: Any) -> str:
    material = {
        "org": str(org_id), "project": str(project_id), "snapshot": str(snapshot_id), "perm": permissions_version,
        "versions": versions or {}, "params": params,
    }
    digest = hashlib.sha256(json.dumps(material, sort_keys=True, default=str).encode()).hexdigest()[:40]
    return f"pm:{namespace}:{digest}"


def cache_get_json(key: str) -> Any | None:
    v = backend().get(key)
    return json.loads(v) if v is not None else None


def cache_set_json(key: str, value: Any, ttl: int = 300) -> None:
    backend().set(key, json.dumps(value, default=str), ttl)


class LimitExceeded(RuntimeError):
    pass


@contextmanager
def semaphore(key: str, limit: int, ttl: int = 900) -> Iterator[None]:
    """Counting semaphore for concurrency limits (per-run LLM calls, environment-wide calls)."""
    b = backend()
    n = b.incr(key, ttl)
    if n > limit:
        b.decr(key)
        raise LimitExceeded(f"limit {limit} reached for {key}")
    try:
        yield
    finally:
        b.decr(key)
