from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    remaining: int
    retry_after_seconds: int


class IRateLimiter(ABC):
    """Fixed-window request-rate limiting (Phase 8 WP5). `key` is the
    caller's caller to build a scoped identity (e.g. `f"auth_login:{ip}"`
    or `f"generate_video:{user_id}"`) - this interface has no opinion on
    identity, only on counting. One call per incoming request; the
    window resets `window_seconds` after the *first* call in that
    window, not on a fixed clock boundary - a real fixed-window counter,
    not a sliding one (simpler, and sufficient for the abuse-protection
    goal here: bound the *rate*, not guarantee perfectly smooth
    distribution)."""

    @abstractmethod
    def allow(self, key: str, *, limit: int, window_seconds: int) -> RateLimitResult: ...


class InMemoryRateLimiter(IRateLimiter):
    def __init__(self) -> None:
        self._counts: dict[str, tuple[int, float]] = {}  # key -> (count, window_end_monotonic)

    def allow(self, key: str, *, limit: int, window_seconds: int) -> RateLimitResult:
        now = time.monotonic()
        count, window_end = self._counts.get(key, (0, 0.0))
        if now >= window_end:
            count, window_end = 0, now + window_seconds
        count += 1
        self._counts[key] = (count, window_end)

        allowed = count <= limit
        retry_after = int(window_end - now) + 1 if not allowed else 0
        return RateLimitResult(allowed=allowed, remaining=max(0, limit - count), retry_after_seconds=retry_after)


class RedisRateLimiter(IRateLimiter):
    """Real Redis-backed `IRateLimiter` (Phase 8 WP5): a fixed-window
    counter via `INCR` + `EXPIRE`, atomic against concurrent requests
    from separate `apps/api` processes since the counter itself lives in
    Redis, not in any one process's memory - fixing the same
    multi-replica gap `InMemoryRateLimiter` has (two processes would
    each allow up to `limit` requests independently, effectively
    doubling the real limit)."""

    def __init__(self, redis_url: str, *, key_prefix: str = "ratelimit:") -> None:
        import redis

        self._client = redis.Redis.from_url(redis_url, decode_responses=True)
        self._key_prefix = key_prefix

    def allow(self, key: str, *, limit: int, window_seconds: int) -> RateLimitResult:
        redis_key = f"{self._key_prefix}{key}:{window_seconds}"
        count = self._client.incr(redis_key)
        ttl = self._client.ttl(redis_key)
        if ttl < 0:
            # First increment on this key (or a key that somehow lost
            # its TTL) - (re)arm the window's expiry now.
            self._client.expire(redis_key, window_seconds)
            ttl = window_seconds

        allowed = count <= limit
        retry_after = ttl if not allowed and ttl > 0 else 0
        return RateLimitResult(allowed=allowed, remaining=max(0, limit - count), retry_after_seconds=retry_after)
