from __future__ import annotations

from abc import ABC, abstractmethod


class ITokenStore(ABC):
    """Bearer-token storage, extracted out of `LocalAuthProvider` (Phase
    8 WP3) so the token itself can live somewhere other than one
    process's memory - the multi-replica gap
    `docs/PHASE8_SCALEOUT_PLAN.md` item 22 named: a token issued by one
    `apps/api` process was never recognized by another, since
    `LocalAuthProvider._tokens` was a plain in-process `dict`."""

    @abstractmethod
    def set(self, token: str, user_id: str) -> None: ...

    @abstractmethod
    def get(self, token: str) -> str | None: ...

    @abstractmethod
    def delete(self, token: str) -> None: ...


class InMemoryTokenStore(ITokenStore):
    """Behaviorally identical to `LocalAuthProvider`'s pre-WP3 internal
    `dict[str, str]` - the default, unchanged for every existing
    environment."""

    def __init__(self) -> None:
        self._tokens: dict[str, str] = {}

    def set(self, token: str, user_id: str) -> None:
        self._tokens[token] = user_id

    def get(self, token: str) -> str | None:
        return self._tokens.get(token)

    def delete(self, token: str) -> None:
        self._tokens.pop(token, None)


class RedisTokenStore(ITokenStore):
    """Real Redis-backed `ITokenStore` (Phase 8 WP3): every `apps/api`
    process (and, in principle, a worker process) reading the same
    Redis server recognizes the same tokens - fixing the multi-replica
    gap `InMemoryTokenStore` can't. `ttl_seconds` maps directly onto
    Redis's own key expiry; token *rotation*/refresh (WP5) is not
    implemented here - this is storage, not the expiry policy."""

    def __init__(self, redis_url: str, *, key_prefix: str = "auth_token:", ttl_seconds: int | None = None) -> None:
        import redis

        self._client = redis.Redis.from_url(redis_url, decode_responses=True)
        self._key_prefix = key_prefix
        self._ttl_seconds = ttl_seconds

    def set(self, token: str, user_id: str) -> None:
        self._client.set(self._key_prefix + token, user_id, ex=self._ttl_seconds)

    def get(self, token: str) -> str | None:
        return self._client.get(self._key_prefix + token)

    def delete(self, token: str) -> None:
        self._client.delete(self._key_prefix + token)
