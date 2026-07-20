from __future__ import annotations

from render_orchestrator import Event, EventType, InMemoryEventBus


def test_publish_records_history():
    bus = InMemoryEventBus()
    bus.publish(Event(type=EventType.PROJECT_CREATED, project_id="proj_1"))
    bus.publish(Event(type=EventType.PLAN_GENERATED, project_id="proj_1", data={"logline": "x"}))

    assert [e.type for e in bus.history] == [EventType.PROJECT_CREATED, EventType.PLAN_GENERATED]


def test_subscribe_receives_matching_events_only():
    bus = InMemoryEventBus()
    received: list[Event] = []
    bus.subscribe(EventType.GENERATION_COMPLETED, received.append)

    bus.publish(Event(type=EventType.PROJECT_CREATED, project_id="proj_1"))
    bus.publish(Event(type=EventType.GENERATION_COMPLETED, project_id="proj_1", data={"asset_ids": ["a1"]}))

    assert len(received) == 1
    assert received[0].data == {"asset_ids": ["a1"]}


def test_multiple_subscribers_all_fire():
    bus = InMemoryEventBus()
    calls = []
    bus.subscribe(EventType.PROJECT_CREATED, lambda e: calls.append("first"))
    bus.subscribe(EventType.PROJECT_CREATED, lambda e: calls.append("second"))

    bus.publish(Event(type=EventType.PROJECT_CREATED, project_id="proj_1"))

    assert calls == ["first", "second"]
