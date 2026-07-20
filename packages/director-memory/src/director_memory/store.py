from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class DirectorMemoryEntry:
    stage: str
    content: dict[str, Any]
    created_at: float = field(default_factory=time.time)


class IDirectorMemoryStore(ABC):
    """Per-project history of every artifact the Creative Director pipeline
    has produced (CreativeBrief, StoryOutline, DirectorPlan, reviewer
    feedback). Exists so a revision loop (storyboard `changes_requested`)
    can re-invoke an earlier stage with full prior context instead of
    starting from the raw idea again - see
    docs/workflows/ai-director-workflow.md.

    This is plain history, not a vector/semantic memory - Phase 1 needs
    "what did we already decide for this project," not similarity search
    across projects. A production-grade persistent implementation
    (Postgres-backed) is a Phase 2+ concern; `InMemoryDirectorMemoryStore`
    is sufficient for local dev and single-process testing.
    """

    @abstractmethod
    def append(self, project_id: str, entry: DirectorMemoryEntry) -> None: ...

    @abstractmethod
    def history(self, project_id: str, stage: str | None = None) -> list[DirectorMemoryEntry]: ...

    @abstractmethod
    def latest(self, project_id: str, stage: str) -> DirectorMemoryEntry | None: ...


class InMemoryDirectorMemoryStore(IDirectorMemoryStore):
    def __init__(self) -> None:
        self._entries: dict[str, list[DirectorMemoryEntry]] = {}

    def append(self, project_id: str, entry: DirectorMemoryEntry) -> None:
        self._entries.setdefault(project_id, []).append(entry)

    def history(self, project_id: str, stage: str | None = None) -> list[DirectorMemoryEntry]:
        entries = self._entries.get(project_id, [])
        if stage is None:
            return list(entries)
        return [entry for entry in entries if entry.stage == stage]

    def latest(self, project_id: str, stage: str) -> DirectorMemoryEntry | None:
        matching = self.history(project_id, stage=stage)
        return matching[-1] if matching else None
