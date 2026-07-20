from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class ProjectStatus(str, Enum):
    """The project-level lifecycle state machine (Phase 4).

    WAITING_STORYBOARD_APPROVAL, WAITING_RENDER_APPROVAL, APPROVED, and
    REJECTED are the exact approval-gate vocabulary; CREATED/PLANNING/
    GENERATING/COMPLETED/FAILED are the surrounding states a complete
    lifecycle needs. See ProjectLifecycle (services/render-orchestrator)
    for the transitions between them.
    """

    CREATED = "created"
    PLANNING = "planning"
    WAITING_STORYBOARD_APPROVAL = "waiting_storyboard_approval"
    WAITING_RENDER_APPROVAL = "waiting_render_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ProjectRecord:
    """The Project persistence entity. Deliberately does NOT embed the
    DirectorPlan/Storyboard/RenderPlan bodies or duplicate the
    GenerationJob/Asset stores - those already have their own
    interface-based, replaceable persistence (IDirectorMemoryStore,
    IGenerationJobStore, AssetManager) from Phases 1-3. ProjectRecord is
    the top-level aggregate the API reads: identity, brief, status, and
    references (job/asset ids) into those other stores. See
    docs/adr/0010-persistence-and-lifecycle.md for why this wasn't
    six separate repositories.
    """

    project_id: str
    workspace_id: str
    created_by: str
    brief: dict[str, Any]
    status: ProjectStatus = ProjectStatus.CREATED
    rejected_stage: str | None = None
    generation_job_ids: list[str] = field(default_factory=list)
    asset_ids: list[str] = field(default_factory=list)
    error_message: str | None = None
    created_at: str = field(default_factory=lambda: _now())
    updated_at: str = field(default_factory=lambda: _now())

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "workspace_id": self.workspace_id,
            "created_by": self.created_by,
            "brief": self.brief,
            "status": self.status.value,
            "rejected_stage": self.rejected_stage,
            "generation_job_ids": self.generation_job_ids,
            "asset_ids": self.asset_ids,
            "error_message": self.error_message,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class IProjectStore(ABC):
    @abstractmethod
    def create(self, record: ProjectRecord) -> None: ...

    @abstractmethod
    def get(self, project_id: str) -> ProjectRecord | None: ...

    @abstractmethod
    def save(self, record: ProjectRecord) -> None: ...

    @abstractmethod
    def list_for_workspace(self, workspace_id: str) -> list[ProjectRecord]: ...


class InMemoryProjectStore(IProjectStore):
    def __init__(self) -> None:
        self._projects: dict[str, ProjectRecord] = {}

    def create(self, record: ProjectRecord) -> None:
        if record.project_id in self._projects:
            raise ValueError(f"Project {record.project_id} already exists")
        self._projects[record.project_id] = record

    def get(self, project_id: str) -> ProjectRecord | None:
        return self._projects.get(project_id)

    def save(self, record: ProjectRecord) -> None:
        record.updated_at = _now()
        self._projects[record.project_id] = record

    def list_for_workspace(self, workspace_id: str) -> list[ProjectRecord]:
        return [p for p in self._projects.values() if p.workspace_id == workspace_id]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
