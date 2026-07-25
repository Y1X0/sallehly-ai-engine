"""Real, live-executed tests for RedisCache (Phase 8 WP3) - driven
against an actual local Redis server, not mocked. InMemoryCache is
tested unconditionally alongside it to confirm both implementations of
ICache agree on behavior.

RedisCache tests are skipped entirely if no Redis server is reachable at
REDIS_URL - see docs/DEV_SETUP.md for how to run one locally.
"""

from __future__ import annotations

import time
import uuid

import pytest
from cache_sdk import ICache, InMemoryCache, RedisCache

REDIS_URL = "redis://localhost:6379/0"


def _redis_reachable() -> bool:
    try:
        import redis

        client = redis.Redis.from_url(REDIS_URL)
        return client.ping()
    except Exception:
        return False


_REDIS_AVAILABLE = _redis_reachable()


def _in_memory() -> ICache:
    return InMemoryCache()


def _redis() -> ICache:
    return RedisCache(REDIS_URL, key_prefix=f"test:{uuid.uuid4().hex[:8]}:")


_IMPLS = [_in_memory] + ([_redis] if _REDIS_AVAILABLE else [])


@pytest.mark.parametrize("make_cache", _IMPLS)
def test_get_missing_returns_none(make_cache):
    cache = make_cache()
    assert cache.get("missing") is None


@pytest.mark.parametrize("make_cache", _IMPLS)
def test_set_and_get_round_trips_json_value(make_cache):
    cache = make_cache()
    cache.set("k1", {"a": 1, "b": [1, 2, 3]})
    assert cache.get("k1") == {"a": 1, "b": [1, 2, 3]}


@pytest.mark.parametrize("make_cache", _IMPLS)
def test_delete_removes_key(make_cache):
    cache = make_cache()
    cache.set("k1", "value")
    cache.delete("k1")
    assert cache.get("k1") is None


@pytest.mark.parametrize("make_cache", _IMPLS)
def test_set_overwrites_existing_value(make_cache):
    cache = make_cache()
    cache.set("k1", "first")
    cache.set("k1", "second")
    assert cache.get("k1") == "second"


@pytest.mark.parametrize("make_cache", _IMPLS)
def test_ttl_expires_the_key(make_cache):
    cache = make_cache()
    cache.set("k1", "value", ttl_seconds=1)
    assert cache.get("k1") == "value"
    time.sleep(1.5)
    assert cache.get("k1") is None


@pytest.mark.skipif(not _REDIS_AVAILABLE, reason=f"no Redis server reachable at {REDIS_URL}")
def test_redis_cache_survives_a_new_instance_against_the_same_server():
    """Proves persistence is real (the key lives in Redis, not just in a
    Python object) by reading it back through a brand new RedisCache
    instance sharing the same key_prefix."""
    prefix = f"test:{uuid.uuid4().hex[:8]}:"
    first = RedisCache(REDIS_URL, key_prefix=prefix)
    first.set("k1", {"hello": "world"})

    second = RedisCache(REDIS_URL, key_prefix=prefix)
    assert second.get("k1") == {"hello": "world"}
