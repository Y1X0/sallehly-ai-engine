from __future__ import annotations

import json
from typing import Any, Callable

import redis

from .events import Event, EventType, IEventBus


class RedisEventBus(IEventBus):
    """Real Redis pub/sub-backed `IEventBus` (Phase 8 WP3). Fixes
    `InMemoryEventBus`'s documented limitation directly: subscribers
    only see events published within the *same process* - the moment
    there's more than one `apps/api` process (or an API process plus a
    separate Temporal worker process, see ADR 0015/0016), in-process
    pub/sub can't deliver across them. `RedisEventBus` can, since every
    instance - regardless of which process constructed it - publishes
    to and subscribes from the same Redis server.

    One Redis channel per `EventType` (`key_prefix + event_type.value`)
    rather than one shared channel with client-side filtering - `redis-py`'s
    `pubsub().subscribe(**{channel: callback})` already dispatches
    per-channel, so this avoids a manual type-filter branch on every
    message. `subscribe()` lazily starts exactly one background listener
    thread (`redis-py`'s own `pubsub.run_in_thread`) on first use, kept
    for the life of this instance.
    """

    def __init__(self, redis_url: str, *, key_prefix: str = "events:") -> None:
        self._client = redis.Redis.from_url(redis_url, decode_responses=True)
        self._pubsub = self._client.pubsub(ignore_subscribe_messages=True)
        self._key_prefix = key_prefix
        self._handlers: dict[EventType, list[Callable[[Event], None]]] = {}
        self._listener_thread: Any = None

    def publish(self, event: Event) -> None:
        self._client.publish(self._channel(event.type), json.dumps(_to_wire(event)))

    def subscribe(self, event_type: EventType, handler: Callable[[Event], None]) -> None:
        is_new_channel = event_type not in self._handlers
        self._handlers.setdefault(event_type, []).append(handler)
        if is_new_channel:
            self._pubsub.subscribe(**{self._channel(event_type): self._make_dispatcher(event_type)})
            if self._listener_thread is None:
                self._listener_thread = self._pubsub.run_in_thread(sleep_time=0.01, daemon=True)

    def close(self) -> None:
        """Stops the background listener thread - not part of
        `IEventBus`, but a real resource (a thread, a socket) that a
        long-lived process should release deliberately rather than
        relying on GC/daemon-thread exit. `stop()` only trips a flag;
        the listener thread's own run loop closes the pub/sub
        connection after its current blocking read returns (redis-py's
        `PubSubWorkerThread.run`) - calling `self._pubsub.close()` here
        too would race that same close from two threads, so `join()`
        instead of closing directly."""
        if self._listener_thread is not None:
            self._listener_thread.stop()
            self._listener_thread.join(timeout=2.0)
            self._listener_thread = None

    def _channel(self, event_type: EventType) -> str:
        return f"{self._key_prefix}{event_type.value}"

    def _make_dispatcher(self, event_type: EventType) -> Callable[[dict], None]:
        def _dispatch(message: dict) -> None:
            event = _from_wire(json.loads(message["data"]))
            for handler in self._handlers.get(event_type, []):
                handler(event)

        return _dispatch


def _to_wire(event: Event) -> dict[str, Any]:
    return {
        "type": event.type.value,
        "project_id": event.project_id,
        "data": event.data,
        "occurred_at": event.occurred_at,
    }


def _from_wire(payload: dict[str, Any]) -> Event:
    return Event(
        type=EventType(payload["type"]),
        project_id=payload["project_id"],
        data=payload["data"],
        occurred_at=payload["occurred_at"],
    )
