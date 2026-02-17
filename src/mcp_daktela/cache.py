"""Simple in-process TTL cache for Daktela reference data.

Caches unfiltered "list all" responses for stable reference endpoints
(users, queues, categories, etc.) to avoid repeated API round-trips.

Cache keys include user identity (URL + username or token) to prevent
data leakage between tenants or users with different permission levels.

Safe for asyncio (single-threaded per event loop, no locking needed).
"""

import os
import time

CACHEABLE_ENDPOINTS = frozenset({
    "users",
    "queues",
    "ticketsCategories",
    "groups",
    "pauses",
    "statuses",
    "templates",
    "campaignsTypes",
})

_DEFAULT_TTL = 3600  # 60 minutes

_store: dict[tuple, tuple[float, dict]] = {}


def _enabled() -> bool:
    return os.environ.get("CACHE_ENABLED", "true").lower() not in ("false", "0", "no")


def _ttl() -> float:
    return float(os.environ.get("CACHE_TTL_SECONDS", _DEFAULT_TTL))


def get(
    identity: tuple,
    endpoint: str,
    skip: int,
    take: int,
    sort: str | None,
    sort_dir: str,
) -> dict | None:
    """Return cached result or None on miss/expired/non-cacheable/disabled."""
    if not _enabled() or endpoint not in CACHEABLE_ENDPOINTS:
        return None
    key = (identity, endpoint, skip, take, sort, sort_dir)
    entry = _store.get(key)
    if entry is None:
        return None
    expires_at, data = entry
    if time.monotonic() > expires_at:
        del _store[key]
        return None
    return data


def put(
    identity: tuple,
    endpoint: str,
    skip: int,
    take: int,
    sort: str | None,
    sort_dir: str,
    data: dict,
) -> None:
    """Cache a result. Silently ignores non-cacheable endpoints or when disabled."""
    if not _enabled() or endpoint not in CACHEABLE_ENDPOINTS:
        return
    # Prune expired entries to prevent unbounded growth
    now = time.monotonic()
    expired = [k for k, (exp, _) in _store.items() if now > exp]
    for k in expired:
        del _store[k]
    _store[(identity, endpoint, skip, take, sort, sort_dir)] = (now + _ttl(), data)


def clear() -> None:
    """Clear all cached data."""
    _store.clear()
