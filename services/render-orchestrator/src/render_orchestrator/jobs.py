from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import schemas


class GenerationJobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class GenerationJob:
    """A single RenderSpec's journey through an IVideoEngine/IComputeProvider
    pair. Mutable (unlike the frozen value objects elsewhere in this
    codebase) because it has identity and evolving state - GenerationPipeline
    updates the same instance's status/error_message/retry_count as it
    progresses, rather than constructing a new one at each step.
    """

    job_id: str
    project_id: str
    shot_id: str
    render_spec: dict[str, Any]
    engine_id: str
    compute_provider_id: str
    status: GenerationJobStatus = GenerationJobStatus.QUEUED
    external_job_id: str | None = None
    output_asset_id: str | None = None
    error_message: str | None = None
    retry_count: int = 0
    created_at: str = field(default_factory=lambda: _now())
    updated_at: str = field(default_factory=lambda: _now())

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": "1.0",
            "job_id": self.job_id,
            "project_id": self.project_id,
            "shot_id": self.shot_id,
            "render_spec": self.render_spec,
            "engine_id": self.engine_id,
            "compute_provider_id": self.compute_provider_id,
            "status": self.status.value,
            "retry_count": self.retry_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if self.external_job_id is not None:
            payload["external_job_id"] = self.external_job_id
        if self.output_asset_id is not None:
            payload["output_asset_id"] = self.output_asset_id
        if self.error_message is not None:
            payload["error_message"] = self.error_message
        return payload

    def validate(self) -> None:
        schemas.validate(self.to_dict(), "generation_job")


class IGenerationJobStore(ABC):
    @abstractmethod
    def save(self, job: GenerationJob) -> None: ...

    @abstractmethod
    def get(self, job_id: str) -> GenerationJob | None: ...

    @abstractmethod
    def list_for_project(self, project_id: str) -> list[GenerationJob]: ...


class InMemoryGenerationJobStore(IGenerationJobStore):
    def __init__(self) -> None:
        self._jobs: dict[str, GenerationJob] = {}

    def save(self, job: GenerationJob) -> None:
        self._jobs[job.job_id] = job

    def get(self, job_id: str) -> GenerationJob | None:
        return self._jobs.get(job_id)

    def list_for_project(self, project_id: str) -> list[GenerationJob]:
        return [job for job in self._jobs.values() if job.project_id == project_id]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
