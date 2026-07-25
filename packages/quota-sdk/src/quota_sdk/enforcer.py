from __future__ import annotations

import threading
from abc import ABC, abstractmethod


class QuotaExceededError(Exception):
    """Raised by `IQuotaEnforcer.acquire()` when `scope` is already at
    its concurrency cap."""


class IQuotaEnforcer(ABC):
    """A concurrency cap, not a rate limit: bounds how many operations
    for a given `scope` (e.g. a workspace id) may be *in flight* at
    once, not how many may *start* per unit time (`IRateLimiter`'s job).
    `docs/PHASE8_SCALEOUT_PLAN.md` items 7 ("a per-workspace/global
    concurrency cap on in-flight generation jobs") and 25
    ("workspace-scoped resource limits") - GPU generation is the
    concrete cost this protects: an unbounded number of simultaneous
    `generate_video` calls from one workspace could exhaust the
    platform's compute capacity or run up an unbounded bill.
    """

    @abstractmethod
    def acquire(self, scope: str, *, max_concurrent: int) -> None:
        """Raises `QuotaExceededError` if `scope` is already at
        `max_concurrent` in-flight operations; otherwise reserves one
        slot. Callers must `release(scope)` in a `finally` block."""

    @abstractmethod
    def release(self, scope: str) -> None: ...


class InMemoryQuotaEnforcer(IQuotaEnforcer):
    def __init__(self) -> None:
        self._counts: dict[str, int] = {}
        self._lock = threading.Lock()

    def acquire(self, scope: str, *, max_concurrent: int) -> None:
        with self._lock:
            current = self._counts.get(scope, 0)
            if current >= max_concurrent:
                raise QuotaExceededError(
                    f"Workspace {scope} already has {current} generation(s) in flight (limit {max_concurrent})"
                )
            self._counts[scope] = current + 1

    def release(self, scope: str) -> None:
        with self._lock:
            current = self._counts.get(scope, 0)
            self._counts[scope] = max(0, current - 1)


_ACQUIRE_SCRIPT = """
local current = tonumber(redis.call('GET', KEYS[1]) or '0')
if current >= tonumber(ARGV[1]) then
    return -1
else
    return redis.call('INCR', KEYS[1])
end
"""


class RedisQuotaEnforcer(IQuotaEnforcer):
    """Real Redis-backed `IQuotaEnforcer` (Phase 8 WP5): the
    check-and-increment happens inside a single Lua script
    (`EVAL`), which Redis executes atomically - two `apps/api`
    processes racing to `acquire()` the same workspace's last slot
    cannot both succeed, unlike a plain `INCR` + check + `DECR`-on-reject
    sequence (which has a real race window between the increment and
    the check)."""

    def __init__(self, redis_url: str, *, key_prefix: str = "quota:") -> None:
        import redis

        self._client = redis.Redis.from_url(redis_url, decode_responses=True)
        self._key_prefix = key_prefix

    def acquire(self, scope: str, *, max_concurrent: int) -> None:
        key = f"{self._key_prefix}{scope}"
        result = int(self._client.eval(_ACQUIRE_SCRIPT, 1, key, str(max_concurrent)))
        if result == -1:
            raise QuotaExceededError(
                f"Workspace {scope} already has {max_concurrent} generation(s) in flight (limit {max_concurrent})"
            )

    def release(self, scope: str) -> None:
        key = f"{self._key_prefix}{scope}"
        new_value = self._client.decr(key)
        if int(new_value) < 0:
            # Never go negative (a release() without a matching acquire()
            # would otherwise let the counter drift below zero, silently
            # granting the workspace extra headroom on a later acquire()).
            self._client.set(key, 0)
