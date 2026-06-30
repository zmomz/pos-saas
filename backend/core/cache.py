"""Tenant-scoped read cache (M10 — issue #219).

Hot reads — brand resolution, per-client feature entitlements, the global tax
rate, and the client dashboard aggregates — are read on nearly every request but
change rarely. Recomputing them from Postgres on every hit makes reads contend
with writes and caps how far the platform scales. This module fronts those reads
with a small cache that:

* uses **Redis** (``redis.asyncio``) when ``REDIS_URL`` is configured — shared
  across every API worker, so an invalidation on one process is seen by all; and
* transparently **degrades to a process-local in-memory store** when Redis is not
  configured, the ``redis`` package is absent, or the server is unreachable. Dev,
  CI and the test suite run with no Redis and still get correct (if per-process)
  caching, so callers never special-case the backend.

Every cached value is JSON-encoded and namespaced under ``pos:cache:v1:``. Keys
are built so that a write can invalidate exactly the tenant it touched — see
``invalidate_prefix`` and the ``*_key`` helpers — which is the "tenant-scoped
invalidation on write" half of the issue: a sale clears one client's dashboard,
a feature toggle clears one client's entitlements, a branding edit clears one
agent's brand, never the whole cache.

Design rules:

* **Never fail the request for a cache problem.** Every backend call is wrapped
  so a Redis hiccup is logged once and treated as a miss — correctness falls back
  to the database, never to an error.
* **Reads are best-effort, invalidation is mandatory.** A missed read just costs
  a recompute; a missed invalidation would serve stale data, so the in-memory
  fallback exists precisely so invalidation always has somewhere to write.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger(__name__)

# Single namespace + schema version for every key this layer owns. Bumping the
# version is a blunt, instant flush of all cached reads after a format change.
KEY_PREFIX = "pos:cache:v1:"

# Default TTLs (seconds). Even with explicit invalidation on write, a TTL bounds
# how long a *missed* invalidation (e.g. a write on another process before Redis
# is wired up) can serve stale data. Aggregates change on every sale, so they get
# the shortest leash; brand/features/tax change rarely.
TTL_BRAND = 600
TTL_FEATURES = 300
TTL_TAX = 300
TTL_DASHBOARD = 30


def _redis_url() -> str:
    """The configured Redis URL, or '' when caching should stay in-process.

    Read from the environment directly (not the cached settings attribute) so a
    test or a redeploy can flip the backend without reconstructing the singleton.
    """
    return (os.getenv("REDIS_URL", "") or "").strip()


class _MemoryBackend:
    """Process-local TTL store used when Redis is not available.

    Correct within one worker; not shared across workers. Good enough for dev/CI
    and as a safety net, and it keeps the invalidation contract intact so callers
    are identical regardless of backend.
    """

    def __init__(self) -> None:
        self._store: dict[str, tuple[float, str]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[str]:
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if expires_at <= time.monotonic():
                self._store.pop(key, None)
                return None
            return value

    async def set(self, key: str, value: str, ttl: int) -> None:
        async with self._lock:
            self._store[key] = (time.monotonic() + max(1, ttl), value)

    async def delete(self, *keys: str) -> None:
        if not keys:
            return
        async with self._lock:
            for key in keys:
                self._store.pop(key, None)

    async def delete_prefix(self, prefix: str) -> None:
        async with self._lock:
            stale = [k for k in self._store if k.startswith(prefix)]
            for key in stale:
                self._store.pop(key, None)


class TenantCache:
    """Façade over whichever backend is active. One module-level instance.

    The backend is chosen lazily on first use so importing this module has no side
    effects (no socket opened at import time) and the test suite — which sets env
    vars before importing the app — sees the right backend.
    """

    def __init__(self) -> None:
        self._memory = _MemoryBackend()
        self._redis: Any = None
        self._redis_initialized = False
        self._init_lock = asyncio.Lock()

    async def _backend(self) -> Any:
        """Return the active backend, building the Redis client once if configured."""
        url = _redis_url()
        if not url:
            return self._memory
        if self._redis_initialized:
            return self._redis or self._memory
        async with self._init_lock:
            if self._redis_initialized:
                return self._redis or self._memory
            self._redis_initialized = True
            try:
                import redis.asyncio as aioredis  # type: ignore

                self._redis = aioredis.from_url(
                    url, encoding="utf-8", decode_responses=True
                )
                logger.info("Cache backend: Redis (%s)", _redacted(url))
            except ImportError:
                logger.warning(
                    "REDIS_URL is set but the 'redis' package is not installed; "
                    "falling back to a process-local cache. Install redis>=5 to "
                    "share the cache across workers."
                )
                self._redis = None
            except Exception:  # pragma: no cover - defensive client construction
                logger.exception("Failed to construct Redis client; using in-memory cache")
                self._redis = None
        return self._redis or self._memory

    @property
    def backend_name(self) -> str:
        """'redis' or 'memory' — for health/diagnostics. Reflects configuration."""
        return "redis" if (_redis_url() and self._redis is not None) else "memory"

    async def get_json(self, key: str) -> Optional[Any]:
        """Return the decoded cached value for ``key``, or ``None`` on miss/error."""
        full = KEY_PREFIX + key
        backend = await self._backend()
        try:
            raw = await backend.get(full)
        except Exception:
            logger.warning("Cache get failed for %s; treating as miss", key, exc_info=True)
            return None
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            logger.warning("Cache value for %s is not valid JSON; ignoring", key)
            return None

    async def set_json(self, key: str, value: Any, ttl: int) -> None:
        """JSON-encode and store ``value`` under ``key`` for ``ttl`` seconds."""
        full = KEY_PREFIX + key
        try:
            raw = json.dumps(value, default=str)
        except (TypeError, ValueError):
            logger.warning("Cache value for %s is not JSON-serializable; not caching", key)
            return
        backend = await self._backend()
        try:
            await backend.set(full, raw, ttl)
        except Exception:
            logger.warning("Cache set failed for %s; skipping", key, exc_info=True)

    async def get_or_load(
        self, key: str, ttl: int, loader: Callable[[], Awaitable[Any]]
    ) -> Any:
        """Return the cached value for ``key``; on miss run ``loader`` and cache it.

        ``loader`` is the authoritative (DB-backed) computation. Its result is
        cached even when falsy/empty so a legitimately-empty answer is not
        recomputed on every hit; ``None`` is the one value we never cache (it is
        indistinguishable from a miss on read).
        """
        cached = await self.get_json(key)
        if cached is not None:
            return cached
        value = await loader()
        if value is not None:
            await self.set_json(key, value, ttl)
        return value

    async def delete(self, *keys: str) -> None:
        """Invalidate exact ``keys`` (best-effort, but the contract callers rely on)."""
        if not keys:
            return
        full = [KEY_PREFIX + k for k in keys]
        backend = await self._backend()
        try:
            await backend.delete(*full)
        except Exception:
            logger.warning("Cache delete failed for %s; skipping", keys, exc_info=True)

    async def invalidate_prefix(self, prefix: str) -> None:
        """Invalidate every key under ``prefix`` — the tenant-scoped flush primitive.

        For Redis this scans with ``MATCH`` (cursor-based, non-blocking) and deletes
        in batches; for the in-memory backend it filters the dict. Either way the
        blast radius is exactly the keys the caller namespaced under ``prefix``.
        """
        full_prefix = KEY_PREFIX + prefix
        backend = await self._backend()
        if isinstance(backend, _MemoryBackend):
            await backend.delete_prefix(full_prefix)
            return
        try:
            batch: list[str] = []
            async for raw_key in backend.scan_iter(match=full_prefix + "*", count=200):
                batch.append(raw_key)
                if len(batch) >= 200:
                    await backend.delete(*batch)
                    batch = []
            if batch:
                await backend.delete(*batch)
        except Exception:
            logger.warning(
                "Cache prefix invalidation failed for %s; skipping", prefix, exc_info=True
            )

    async def reset(self) -> None:
        """Drop the process-local store and forget any Redis client (test hook)."""
        self._memory = _MemoryBackend()
        client = self._redis
        self._redis = None
        self._redis_initialized = False
        if client is not None:
            try:
                await client.aclose()
            except Exception:  # pragma: no cover - best-effort teardown
                pass


def _redacted(url: str) -> str:
    """Hide any credentials in a Redis URL before it reaches a log line."""
    if "@" in url:
        scheme, _, rest = url.partition("://")
        return f"{scheme}://***@{rest.split('@', 1)[1]}" if scheme else "***"
    return url


# Module-level singleton — import and use directly:
#   from core.cache import cache
#   await cache.get_or_load(...)
cache = TenantCache()


# ---------- Tenant-scoped key builders ----------
# Centralizing key shapes here keeps the read site and the write-time
# invalidation site in agreement: a brand edit invalidates exactly what a brand
# read populated.

def brand_agent_key(agent_id: int) -> str:
    """Branding resolved by agent id (agent/client branding reads)."""
    return f"brand:agent:{agent_id}"


def brand_domain_key(domain: str) -> str:
    """Branding resolved by the public custom domain (by-domain lookup)."""
    return f"brand:domain:{(domain or '').strip().lower()}"


def features_prefix(client_id: int) -> str:
    """Prefix covering every feature-entitlement key for one client."""
    return f"features:{client_id}:"


def feature_key(client_id: int, feature_name: str) -> str:
    """One client's entitlement for one feature."""
    return f"{features_prefix(client_id)}{feature_name}"


def tax_global_key() -> str:
    """The platform-wide (master-set) VAT rate — a single global entry."""
    return "tax:global_rate"


def dashboard_key(client_id: int) -> str:
    """One client's dashboard aggregate snapshot."""
    return f"dashboard:{client_id}"


# ---------- Invalidation helpers (call these from write paths) ----------

async def invalidate_brand(
    agent_id: Optional[int] = None, *domains: Optional[str]
) -> None:
    """Clear an agent's cached brand (and any custom domains that pointed at it)."""
    keys: list[str] = []
    if agent_id is not None:
        keys.append(brand_agent_key(agent_id))
    for domain in domains:
        if domain:
            keys.append(brand_domain_key(domain))
    if keys:
        await cache.delete(*keys)


async def invalidate_features(client_id: int) -> None:
    """Clear every feature entitlement cached for one client."""
    await cache.invalidate_prefix(features_prefix(client_id))


async def invalidate_tax() -> None:
    """Clear the global VAT rate (master changed it)."""
    await cache.delete(tax_global_key())


async def invalidate_dashboard(client_id: Optional[int]) -> None:
    """Clear one client's dashboard aggregate snapshot (a sale / catalog write)."""
    if client_id is not None:
        await cache.delete(dashboard_key(int(client_id)))
