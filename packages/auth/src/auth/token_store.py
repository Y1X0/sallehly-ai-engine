from __future__ import annotations

import time
from abc import ABC, abstractmethod


class ITokenStore(ABC):
    """Bearer-token storage, extracted out of `LocalAuthProvider` (Phase
    8 WP3) so the token itself can live somewhere other than one
    process's memory - the multi-replica gap
    `docs/PHASE8_SCALEOUT_PLAN.md` item 22 named: a token issued by one
    `apps/api` process was never recognized by another, since
    `LocalAuthProvider._tokens` was a plain in-process `dict`.

    `set()`'s `ttl_seconds` (Phase 8 WP5, `docs/adr/0020-security-hardening.md`)
    mirrors `ICache.set()`'s exact shape (`packages/cache-sdk`) - `None`
    (the default) means "never expires," unchanged from every pre-WP5
    caller.
    """

    @abstractmethod
    def set(self, token: str, user_id: str, *, ttl_seconds: int | None = None) -> None: ...

    @abstractmethod
    def get(self, token: str) -> str | None: ...

    @abstractmethod
    def delete(self, token: str) -> None: ...


class InMemoryTokenStore(ITokenStore):
    """Behaviorally identical to `LocalAuthProvider`'s pre-WP3 internal
    `dict[str, str]` when `ttl_seconds` is never passed - the default,
    unchanged for every existing environment. `ttl_seconds` is enforced
    with an application-level expiry check on `get()`, the same pattern
    `InMemoryCache` (`packages/cache-sdk`) already uses."""

    def __init__(self) -> None:
        self._tokens: dict[str, str] = {}
        self._expires_at: dict[str, float] = {}

    def set(self, token: str, user_id: str, *, ttl_seconds: int | None = None) -> None:
        self._tokens[token] = user_id
        if ttl_seconds is not None:
            self._expires_at[token] = time.monotonic() + ttl_seconds
        else:
            self._expires_at.pop(token, None)

    def get(self, token: str) -> str | None:
        expires_at = self._expires_at.get(token)
        if expires_at is not None and expires_at <= time.monotonic():
            self._tokens.pop(token, None)
            self._expires_at.pop(token, None)
            return None
        return self._tokens.get(token)

    def delete(self, token: str) -> None:
        self._tokens.pop(token, None)
        self._expires_at.pop(token, None)


class RedisTokenStore(ITokenStore):
    """Real Redis-backed `ITokenStore` (Phase 8 WP3): every `apps/api`
    process (and, in principle, a worker process) reading the same
    Redis server recognizes the same tokens - fixing the multi-replica
    gap `InMemoryTokenStore` can't. `ttl_seconds` maps directly onto
    Redis's own key expiry (`SET ... EX`), per-call, mirroring
    `ICache.set()`'s shape - the constructor's own `ttl_seconds` (kept
    for backward compatibility) is used only when a `set()` call doesn't
    supply its own."""

    def __init__(self, redis_url: str, *, key_prefix: str = "auth_token:", ttl_seconds: int | None = None) -> None:
        import redis

        self._client = redis.Redis.from_url(redis_url, decode_responses=True)
        self._key_prefix = key_prefix
        self._default_ttl_seconds = ttl_seconds

    def set(self, token: str, user_id: str, *, ttl_seconds: int | None = None) -> None:
        effective_ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl_seconds
        self._client.set(self._key_prefix + token, user_id, ex=effective_ttl)

    def get(self, token: str) -> str | None:
        return self._client.get(self._key_prefix + token)

    def delete(self, token: str) -> None:
        self._client.delete(self._key_prefix + token)
