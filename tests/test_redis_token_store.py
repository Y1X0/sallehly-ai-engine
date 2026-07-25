"""Real, live-executed tests for RedisTokenStore (Phase 8 WP3) - driven
against an actual local Redis server, not mocked. Also proves
LocalAuthProvider works unchanged when a RedisTokenStore is injected in
place of the default InMemoryTokenStore.

Skipped entirely if no Redis server is reachable at REDIS_URL - see
docs/DEV_SETUP.md for how to run one locally.
"""

from __future__ import annotations

import time
import uuid

import pytest
from auth import InMemoryUserStore, LocalAuthProvider, RedisTokenStore

REDIS_URL = "redis://localhost:6379/0"


def _redis_reachable() -> bool:
    try:
        import redis

        return redis.Redis.from_url(REDIS_URL).ping()
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _redis_reachable(), reason=f"no Redis server reachable at {REDIS_URL}")


@pytest.fixture
def key_prefix() -> str:
    return f"test:{uuid.uuid4().hex[:8]}:"


def test_set_and_get(key_prefix):
    store = RedisTokenStore(REDIS_URL, key_prefix=key_prefix)
    store.set("tok1", "user1")
    assert store.get("tok1") == "user1"


def test_get_missing_returns_none(key_prefix):
    store = RedisTokenStore(REDIS_URL, key_prefix=key_prefix)
    assert store.get("does-not-exist") is None


def test_delete(key_prefix):
    store = RedisTokenStore(REDIS_URL, key_prefix=key_prefix)
    store.set("tok1", "user1")
    store.delete("tok1")
    assert store.get("tok1") is None


def test_ttl_expires_the_token(key_prefix):
    store = RedisTokenStore(REDIS_URL, key_prefix=key_prefix, ttl_seconds=1)
    store.set("tok1", "user1")
    assert store.get("tok1") == "user1"
    time.sleep(1.5)
    assert store.get("tok1") is None


def test_survives_a_new_instance_against_the_same_server(key_prefix):
    """Proves persistence is real - the multi-replica gap
    InMemoryTokenStore has (a token issued by one process is unrecognized
    by another) directly fixed."""
    first = RedisTokenStore(REDIS_URL, key_prefix=key_prefix)
    first.set("tok1", "user1")

    second = RedisTokenStore(REDIS_URL, key_prefix=key_prefix)
    assert second.get("tok1") == "user1"


def test_local_auth_provider_with_injected_redis_token_store(key_prefix):
    """LocalAuthProvider itself, not just RedisTokenStore in isolation -
    proves the wiring (ITokenStore.set/get calls, not a raw dict) is
    correct end-to-end."""
    user_store = InMemoryUserStore()
    token_store = RedisTokenStore(REDIS_URL, key_prefix=key_prefix)
    provider = LocalAuthProvider(user_store, token_store=token_store)

    provider.register("user@example.com", "correct horse battery staple")
    token = provider.authenticate("user@example.com", "correct horse battery staple")

    user = provider.verify_token(token.token)
    assert user is not None
    assert user.email == "user@example.com"

    # A second provider instance sharing the same Redis-backed store
    # (and the same user_store, matching real deployment where the user
    # store would also be shared - Postgres, WP2) recognizes the token
    # issued by the first, unlike two InMemoryTokenStore instances.
    second_provider = LocalAuthProvider(user_store, token_store=RedisTokenStore(REDIS_URL, key_prefix=key_prefix))
    assert second_provider.verify_token(token.token) is not None
