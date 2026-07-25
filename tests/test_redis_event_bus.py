"""Real, live-executed tests for RedisEventBus (Phase 8 WP3) - driven
against an actual local Redis server, not mocked.

Skipped entirely if no Redis server is reachable at REDIS_URL - see
docs/DEV_SETUP.md for how to run one locally.
"""

from __future__ import annotations

import threading
import time
import uuid

import pytest
from render_orchestrator import Event, EventType
from render_orchestrator.redis_event_bus import RedisEventBus

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


def _wait_for(predicate, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def test_publish_and_subscribe_within_one_instance(key_prefix):
    bus = RedisEventBus(REDIS_URL, key_prefix=key_prefix)
    received: list[Event] = []
    bus.subscribe(EventType.PROJECT_CREATED, received.append)

    event = Event(type=EventType.PROJECT_CREATED, project_id="p1", data={"x": 1})
    bus.publish(event)

    assert _wait_for(lambda: len(received) == 1)
    assert received[0].type == EventType.PROJECT_CREATED
    assert received[0].project_id == "p1"
    assert received[0].data == {"x": 1}
    bus.close()


def test_only_subscribed_event_type_is_delivered(key_prefix):
    bus = RedisEventBus(REDIS_URL, key_prefix=key_prefix)
    received: list[Event] = []
    bus.subscribe(EventType.PLAN_GENERATED, received.append)

    bus.publish(Event(type=EventType.PROJECT_CREATED, project_id="p1"))
    bus.publish(Event(type=EventType.PLAN_GENERATED, project_id="p1"))

    assert _wait_for(lambda: len(received) == 1)
    time.sleep(0.2)
    assert len(received) == 1
    assert received[0].type == EventType.PLAN_GENERATED
    bus.close()


def test_multiple_handlers_for_the_same_event_type_all_fire(key_prefix):
    bus = RedisEventBus(REDIS_URL, key_prefix=key_prefix)
    calls_a: list[Event] = []
    calls_b: list[Event] = []
    bus.subscribe(EventType.RENDER_READY, calls_a.append)
    bus.subscribe(EventType.RENDER_READY, calls_b.append)

    bus.publish(Event(type=EventType.RENDER_READY, project_id="p1"))

    assert _wait_for(lambda: len(calls_a) == 1 and len(calls_b) == 1)
    bus.close()


def test_delivery_across_two_separate_instances(key_prefix):
    """Proves this is real cross-process-capable delivery, not just
    in-process dispatch: the publisher and the subscriber are two
    independent RedisEventBus instances (independent redis-py clients,
    independent sockets) sharing only the same Redis server and
    key_prefix - simulating an API process and a Temporal worker process
    (ADR 0015's own documented limitation) seeing the same event."""
    publisher = RedisEventBus(REDIS_URL, key_prefix=key_prefix)
    subscriber = RedisEventBus(REDIS_URL, key_prefix=key_prefix)
    received: list[Event] = []
    subscriber.subscribe(EventType.GENERATION_COMPLETED, received.append)

    time.sleep(0.1)  # let the subscriber's listener thread actually attach
    publisher.publish(Event(type=EventType.GENERATION_COMPLETED, project_id="p2", data={"shots": 3}))

    assert _wait_for(lambda: len(received) == 1)
    assert received[0].project_id == "p2"
    assert received[0].data == {"shots": 3}
    publisher.close()
    subscriber.close()


def test_handler_runs_on_the_background_listener_thread(key_prefix):
    """A real behavioral consequence worth locking in: handlers execute
    on RedisEventBus's own listener thread, not the publisher's thread -
    unlike InMemoryEventBus, where publish() calls handlers synchronously
    on the caller's own thread."""
    bus = RedisEventBus(REDIS_URL, key_prefix=key_prefix)
    handler_thread_id = []
    done = threading.Event()

    def handler(event: Event) -> None:
        handler_thread_id.append(threading.get_ident())
        done.set()

    bus.subscribe(EventType.EXPORT_COMPLETED, handler)
    bus.publish(Event(type=EventType.EXPORT_COMPLETED, project_id="p1"))

    assert done.wait(timeout=5.0)
    assert handler_thread_id[0] != threading.get_ident()
    bus.close()
