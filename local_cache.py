"""
Simple in-memory cache — no external service, no Redis, no network calls.
Lives entirely in this process's RAM as a plain dict.

Trade-offs vs. the Upstash Redis version (cache_service.py):
- Cache is wiped on every server restart (including every --reload
  auto-restart during dev). Fine for a portfolio project; would matter more
  under --workers > 1 or a production deploy that restarts frequently.
- Not shared across multiple worker processes — each worker gets its own
  cache. This project runs a single uvicorn worker, so that limitation
  doesn't currently apply.
- No network round-trip, so reads/writes are faster than the Redis version.

Exposes the SAME function names/signatures as cache_service.py
(cache_get, cache_set, nl_search_key, summary_key) so switching between
the two later is a one-line import change in ai_service.py, not a rewrite.

Uses functools.lru_cache-style eviction (oldest entry dropped once
MAX_ENTRIES is exceeded) implemented manually via OrderedDict, since
lru_cache itself doesn't support TTL or async functions cleanly.
"""

import hashlib
import time
from collections import OrderedDict

MAX_ENTRIES = 256  # cap memory usage — oldest entry evicted past this

# key -> (value: dict, expires_at: float)
_cache: "OrderedDict[str, tuple[dict, float]]" = OrderedDict()


def _make_key(prefix: str, *parts: str) -> str:
    raw = "|".join(parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}:{digest}"


async def cache_get(key: str) -> dict | None:
    """Returns the cached value, or None on miss/expiry. Async to match the
    Redis version's interface, even though this does no actual I/O."""
    entry = _cache.get(key)
    if entry is None:
        return None

    value, expires_at = entry
    if time.monotonic() > expires_at:
        del _cache[key]
        return None

    _cache.move_to_end(key)  # mark as recently used
    return value


async def cache_set(key: str, value: dict, ttl_seconds: int = 3600) -> None:
    """Stores a value with a TTL. Evicts the oldest entry if over capacity."""
    _cache[key] = (value, time.monotonic() + ttl_seconds)
    _cache.move_to_end(key)

    while len(_cache) > MAX_ENTRIES:
        _cache.popitem(last=False)  # drop oldest (least recently used)


def nl_search_key(question: str) -> str:
    return _make_key("nlsql", question.strip().lower())


def summary_key(event_ids: list[int], limit: int) -> str:
    # Event IDs are globally unique, so hashing them is inherently scoped
    # correctly. Including the ID list means the key naturally changes
    # the moment a new event is created or an old one deleted.
    ids_str = ",".join(str(i) for i in sorted(event_ids))
    return _make_key("summary", ids_str, str(limit))
