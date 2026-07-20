from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable


class EventType(str, Enum):
    PROJECT_CREATED = "project_created"
    PLAN_GENERATED = "plan_generated"
    STORYBOARD_READY = "storyboard_ready"
    RENDER_READY = "render_ready"
    GENERATION_STARTED = "generation_started"
    GENERATION_COMPLETED = "generation_completed"
    GENERATION_FAILED = "generation_failed"


@dataclass(frozen=True)
class Event:
    type: EventType
    project_id: str
    data: dict[str, Any] = field(default_factory=dict)
    occurred_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class IEventBus(ABC):
    """Internal event system (Phase 4): ProjectLifecycle publishes one of
    these at every stage transition. No external delivery (webhooks,
    message queue) is wired up yet - this is the same "prepare the
    abstraction, ship an in-memory implementation" pattern as every other
    interface in this codebase (IDirectorMemoryStore, IGenerationJobStore,
    IComputeProvider, ...). A future NATS/Kafka-backed IEventBus would
    let the API layer's webhook notifications (docs/api/README.md) and
    an eventual notification service subscribe without ProjectLifecycle
    changing at all.
    """

    @abstractmethod
    def publish(self, event: Event) -> None: ...

    @abstractmethod
    def subscribe(self, event_type: EventType, handler: Callable[[Event], None]) -> None: ...


class InMemoryEventBus(IEventBus):
    def __init__(self) -> None:
        self._handlers: dict[EventType, list[Callable[[Event], None]]] = {}
        self.history: list[Event] = []

    def publish(self, event: Event) -> None:
        self.history.append(event)
        for handler in self._handlers.get(event.type, []):
            handler(event)

    def subscribe(self, event_type: EventType, handler: Callable[[Event], None]) -> None:
        self._handlers.setdefault(event_type, []).append(handler)
