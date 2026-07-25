from __future__ import annotations

import json
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from ..config import TrainingConfig
from .budget import CostGuard
from .errors import UnapprovedConfigOverrideError


class ExperimentTier(str, Enum):
    """Which lane of the 3-phase training-factory workflow a job runs in.
    Only PAID_GPU ever needs to pass through CostGuard."""

    FREE_CPU = "free_cpu"
    FREE_GPU = "free_gpu"
    PAID_GPU = "paid_gpu"


class JobStatus(str, Enum):
    PLANNED = "planned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ExperimentConfigGenerator:
    """Generates a new TrainingConfig by applying a small set of top-level
    scalar overrides (e.g. learning_rate, max_train_steps, batch_size) to
    a base config via dataclasses.replace(), but only within human-set
    `allowed_ranges` - the concrete enforcement of the architecture
    report's "AI can vary experiments within pre-approved ranges only"
    boundary. Trying to push a field outside the range a human configured
    raises UnapprovedConfigOverrideError instead of silently clamping, so
    an out-of-range request is never quietly reinterpreted as something
    the human didn't actually approve.

    Deliberately does not accept overrides to `lora` (rank/alpha/target
    modules) or `strategy` - changing fine-tuning method or LoRA rank
    tier is a strategic call the architecture report keeps in the
    human-approval column, not a routine experiment variation."""

    def __init__(self, allowed_ranges: dict[str, tuple[float, float]]) -> None:
        self._allowed_ranges = dict(allowed_ranges)

    def generate_variant(self, base: TrainingConfig, overrides: dict[str, Any]) -> TrainingConfig:
        for field_name, value in overrides.items():
            if field_name not in self._allowed_ranges:
                raise UnapprovedConfigOverrideError(
                    f"'{field_name}' has no configured allowed_range - it cannot be overridden "
                    "by an automated experiment. Add it to allowed_ranges explicitly to permit this."
                )
            low, high = self._allowed_ranges[field_name]
            if not (low <= value <= high):
                raise UnapprovedConfigOverrideError(
                    f"Override {field_name}={value} is outside the human-approved range "
                    f"[{low}, {high}]"
                )

        candidate = replace(base, **overrides)
        candidate.validate()
        return candidate


@dataclass
class JobRecord:
    job_id: str
    tier: ExperimentTier
    provider: str
    config: TrainingConfig
    status: JobStatus = JobStatus.PLANNED
    created_at: datetime = None  # type: ignore[assignment]
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result_summary: str | None = None
    error_message: str | None = None
    estimated_cost_usd: float = 0.0

    def __post_init__(self) -> None:
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "tier": self.tier.value,
            "provider": self.provider,
            "config": self.config.to_dict(),
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "result_summary": self.result_summary,
            "error_message": self.error_message,
            "estimated_cost_usd": self.estimated_cost_usd,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "JobRecord":
        return cls(
            job_id=data["job_id"],
            tier=ExperimentTier(data["tier"]),
            provider=data["provider"],
            config=TrainingConfig.from_dict(data["config"]),
            status=JobStatus(data["status"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            result_summary=data.get("result_summary"),
            error_message=data.get("error_message"),
            estimated_cost_usd=data.get("estimated_cost_usd", 0.0),
        )


class IJobStatusStore(ABC):
    @abstractmethod
    def save(self, job: JobRecord) -> None: ...

    @abstractmethod
    def get(self, job_id: str) -> JobRecord | None: ...

    @abstractmethod
    def list_all(self) -> list[JobRecord]: ...


class InMemoryJobStatusStore(IJobStatusStore):
    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}

    def save(self, job: JobRecord) -> None:
        self._jobs[job.job_id] = job

    def get(self, job_id: str) -> JobRecord | None:
        return self._jobs.get(job_id)

    def list_all(self) -> list[JobRecord]:
        return list(self._jobs.values())


class FilesystemJobStatusStore(IJobStatusStore):
    def __init__(self, root_dir: Path) -> None:
        self._root = root_dir
        self._root.mkdir(parents=True, exist_ok=True)

    def save(self, job: JobRecord) -> None:
        self._path_for(job.job_id).write_text(json.dumps(job.to_dict(), indent=2))

    def get(self, job_id: str) -> JobRecord | None:
        path = self._path_for(job_id)
        if not path.exists():
            return None
        return JobRecord.from_dict(json.loads(path.read_text()))

    def list_all(self) -> list[JobRecord]:
        return [
            JobRecord.from_dict(json.loads(p.read_text()))
            for p in sorted(self._root.glob("*.json"))
        ]

    def _path_for(self, job_id: str) -> Path:
        return self._root / f"{job_id}.json"


class ResultReporter:
    """Turns a JobRecord (+ an optional QualityReport-shaped dict from
    services/training/evaluation) into a markdown summary. Deliberately
    returns plain text rather than calling any GitHub API itself - the
    calling GitHub Actions step is responsible for posting it (e.g. via
    `gh pr comment` or actions/github-script), keeping this package free
    of a GitHub API dependency it doesn't otherwise need."""

    @staticmethod
    def build_report(job: JobRecord, *, quality_summary: dict[str, Any] | None = None) -> str:
        lines = [
            f"### Training automation report - `{job.job_id}`",
            "",
            f"- **Tier:** {job.tier.value}",
            f"- **Provider:** {job.provider}",
            f"- **Status:** {job.status.value}",
            f"- **Base model:** {job.config.base_model_id}",
            f"- **Strategy:** {job.config.strategy}",
            f"- **Created:** {job.created_at.isoformat()}",
        ]
        if job.started_at:
            lines.append(f"- **Started:** {job.started_at.isoformat()}")
        if job.completed_at:
            lines.append(f"- **Completed:** {job.completed_at.isoformat()}")
        if job.tier == ExperimentTier.PAID_GPU:
            lines.append(f"- **Estimated cost:** ${job.estimated_cost_usd:.2f}")
        if job.error_message:
            lines.append(f"- **Error:** {job.error_message}")
        if job.result_summary:
            lines.append("")
            lines.append(job.result_summary)
        if quality_summary:
            lines.append("")
            lines.append("**Quality metrics:**")
            for key, value in quality_summary.items():
                lines.append(f"- {key}: {value}")
        return "\n".join(lines)


class TrainingController:
    """The orchestration point the "AI training controller" requirement
    maps to: plans an experiment's config, enforces the paid-tier
    approval gate via CostGuard before a PAID_GPU job is ever allowed to
    exist in a non-rejected state, tracks status transitions, and builds
    the human-facing report. It never talks to Kaggle/Modal/RunPod
    directly - KaggleClient/ModalJobLauncher/whatever paid provider is in
    use are handed to (or invoked by) the caller after plan_experiment()
    returns successfully.
    """

    def __init__(
        self,
        *,
        job_store: IJobStatusStore,
        config_generator: ExperimentConfigGenerator,
        cost_guard: CostGuard | None = None,
    ) -> None:
        self._jobs = job_store
        self._config_generator = config_generator
        self._cost_guard = cost_guard

    def plan_experiment(
        self,
        *,
        base_config: TrainingConfig,
        overrides: dict[str, Any],
        tier: ExperimentTier,
        provider: str,
        estimated_cost_usd: float = 0.0,
        job_id: str | None = None,
    ) -> JobRecord:
        config = self._config_generator.generate_variant(base_config, overrides)
        job_id = job_id or f"job_{uuid.uuid4().hex[:12]}"

        if tier == ExperimentTier.PAID_GPU:
            if self._cost_guard is None:
                raise UnapprovedConfigOverrideError(
                    "TrainingController has no CostGuard configured - a PAID_GPU job cannot be "
                    "planned without cost protection wired in."
                )
            # Raises ApprovalRequiredError / BudgetExceededError if not
            # cleared - this call is the actual "never start a paid job
            # without approval" enforcement point.
            self._cost_guard.authorize_paid_job(job_id, estimated_cost_usd)

        job = JobRecord(
            job_id=job_id,
            tier=tier,
            provider=provider,
            config=config,
            estimated_cost_usd=estimated_cost_usd,
        )
        self._jobs.save(job)
        return job

    def mark_started(self, job_id: str) -> JobRecord:
        job = self._require_job(job_id)
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)
        self._jobs.save(job)
        return job

    def mark_completed(self, job_id: str, *, result_summary: str) -> JobRecord:
        job = self._require_job(job_id)
        job.status = JobStatus.COMPLETED
        job.completed_at = datetime.now(timezone.utc)
        job.result_summary = result_summary
        self._jobs.save(job)
        if self._cost_guard is not None and job.tier == ExperimentTier.PAID_GPU:
            self._cost_guard.record_actual_spend(
                job_id, provider=job.provider, amount_usd=job.estimated_cost_usd,
            )
        return job

    def mark_failed(self, job_id: str, *, error_message: str) -> JobRecord:
        job = self._require_job(job_id)
        job.status = JobStatus.FAILED
        job.completed_at = datetime.now(timezone.utc)
        job.error_message = error_message
        self._jobs.save(job)
        return job

    def report(self, job_id: str, *, quality_summary: dict[str, Any] | None = None) -> str:
        job = self._require_job(job_id)
        return ResultReporter.build_report(job, quality_summary=quality_summary)

    def _require_job(self, job_id: str) -> JobRecord:
        job = self._jobs.get(job_id)
        if job is None:
            raise KeyError(f"No job found for job_id={job_id!r}")
        return job
