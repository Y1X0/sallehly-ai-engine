from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from typing import Any


class ICache(ABC):
    """Generic key/value cache abstraction (Phase 8 WP3). Values must be
    JSON-serializable - both implementations round-trip through
    `json.dumps`/`json.loads` (even `InMemoryCache`, deliberately, so
    switching to `RedisCache` never surfaces a serialization bug that
    was hidden by `InMemoryCache` storing the live Python object)."""

    @abstractmethod
    def get(self, key: str) -> Any | None: ...

    @abstractmethod
    def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...


class InMemoryCache(ICache):
    def __init__(self) -> None:
        self._values: dict[str, str] = {}
        self._expires_at: dict[str, float] = {}

    def get(self, key: str) -> Any | None:
        expires_at = self._expires_at.get(key)
        if expires_at is not None and expires_at <= time.monotonic():
            self._values.pop(key, None)
            self._expires_at.pop(key, None)
            return None
        raw = self._values.get(key)
        return json.loads(raw) if raw is not None else None

    def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        self._values[key] = json.dumps(value)
        if ttl_seconds is not None:
            self._expires_at[key] = time.monotonic() + ttl_seconds
        else:
            self._expires_at.pop(key, None)

    def delete(self, key: str) -> None:
        self._values.pop(key, None)
        self._expires_at.pop(key, None)


class RedisCache(ICache):
    """Real Redis-backed `ICache` (Phase 8 WP3) - `SET`/`GET`/`DEL`, with
    `ttl_seconds` mapped directly to Redis's own key expiry (`EX`) rather
    than an application-level expiry check, unlike `InMemoryCache`."""

    def __init__(self, redis_url: str, *, key_prefix: str = "cache:") -> None:
        import redis

        self._client = redis.Redis.from_url(redis_url, decode_responses=True)
        self._key_prefix = key_prefix

    def get(self, key: str) -> Any | None:
        raw = self._client.get(self._key_prefix + key)
        return json.loads(raw) if raw is not None else None

    def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        self._client.set(self._key_prefix + key, json.dumps(value), ex=ttl_seconds)

    def delete(self, key: str) -> None:
        self._client.delete(self._key_prefix + key)
