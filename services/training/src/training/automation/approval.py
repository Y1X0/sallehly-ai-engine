from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass
class ApprovalRecord:
    """One human decision on one paid-GPU job request. `job_id` ties this
    back to a TrainingController JobRecord. `max_cost_usd` is the ceiling
    the human is approving - CostGuard checks the job's estimated cost
    against this, not just against the overall monthly budget, so a human
    approving "run A" can't be silently reinterpreted as approving a much
    more expensive "run B"."""

    job_id: str
    requested_by: str
    max_cost_usd: float
    status: ApprovalStatus = ApprovalStatus.PENDING
    approved_by: str | None = None
    reason: str | None = None
    requested_at: datetime = None  # type: ignore[assignment]
    decided_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.requested_at is None:
            self.requested_at = datetime.now(timezone.utc)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["status"] = self.status.value
        data["requested_at"] = self.requested_at.isoformat()
        data["decided_at"] = self.decided_at.isoformat() if self.decided_at else None
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "ApprovalRecord":
        return cls(
            job_id=data["job_id"],
            requested_by=data["requested_by"],
            max_cost_usd=data["max_cost_usd"],
            status=ApprovalStatus(data["status"]),
            approved_by=data.get("approved_by"),
            reason=data.get("reason"),
            requested_at=datetime.fromisoformat(data["requested_at"]),
            decided_at=datetime.fromisoformat(data["decided_at"]) if data.get("decided_at") else None,
        )


class IApprovalStore(ABC):
    @abstractmethod
    def request(self, record: ApprovalRecord) -> None: ...

    @abstractmethod
    def get(self, job_id: str) -> ApprovalRecord | None: ...

    @abstractmethod
    def approve(self, job_id: str, *, approved_by: str, reason: str | None = None) -> ApprovalRecord: ...

    @abstractmethod
    def reject(self, job_id: str, *, approved_by: str, reason: str | None = None) -> ApprovalRecord: ...


class InMemoryApprovalStore(IApprovalStore):
    def __init__(self) -> None:
        self._records: dict[str, ApprovalRecord] = {}

    def request(self, record: ApprovalRecord) -> None:
        if record.job_id in self._records:
            raise ValueError(f"An approval request already exists for job_id={record.job_id!r}")
        self._records[record.job_id] = record

    def get(self, job_id: str) -> ApprovalRecord | None:
        return self._records.get(job_id)

    def approve(self, job_id: str, *, approved_by: str, reason: str | None = None) -> ApprovalRecord:
        return self._decide(job_id, ApprovalStatus.APPROVED, approved_by=approved_by, reason=reason)

    def reject(self, job_id: str, *, approved_by: str, reason: str | None = None) -> ApprovalRecord:
        return self._decide(job_id, ApprovalStatus.REJECTED, approved_by=approved_by, reason=reason)

    def _decide(
        self, job_id: str, status: ApprovalStatus, *, approved_by: str, reason: str | None,
    ) -> ApprovalRecord:
        record = self._records.get(job_id)
        if record is None:
            raise KeyError(f"No approval request found for job_id={job_id!r}")
        record.status = status
        record.approved_by = approved_by
        record.reason = reason
        record.decided_at = datetime.now(timezone.utc)
        return record


class FilesystemApprovalStore(IApprovalStore):
    """Persists one JSON file per job_id under `root_dir` - this is the
    store a GitHub Actions "manual approval gate" job writes to (a human
    clicking Approve in a required-reviewers Environment) and the
    TrainingController reads from before dispatching a paid job."""

    def __init__(self, root_dir: Path) -> None:
        self._root = root_dir
        self._root.mkdir(parents=True, exist_ok=True)

    def request(self, record: ApprovalRecord) -> None:
        path = self._path_for(record.job_id)
        if path.exists():
            raise ValueError(f"An approval request already exists for job_id={record.job_id!r}")
        path.write_text(json.dumps(record.to_dict(), indent=2))

    def get(self, job_id: str) -> ApprovalRecord | None:
        path = self._path_for(job_id)
        if not path.exists():
            return None
        return ApprovalRecord.from_dict(json.loads(path.read_text()))

    def approve(self, job_id: str, *, approved_by: str, reason: str | None = None) -> ApprovalRecord:
        return self._decide(job_id, ApprovalStatus.APPROVED, approved_by=approved_by, reason=reason)

    def reject(self, job_id: str, *, approved_by: str, reason: str | None = None) -> ApprovalRecord:
        return self._decide(job_id, ApprovalStatus.REJECTED, approved_by=approved_by, reason=reason)

    def _decide(
        self, job_id: str, status: ApprovalStatus, *, approved_by: str, reason: str | None,
    ) -> ApprovalRecord:
        record = self.get(job_id)
        if record is None:
            raise KeyError(f"No approval request found for job_id={job_id!r}")
        record.status = status
        record.approved_by = approved_by
        record.reason = reason
        record.decided_at = datetime.now(timezone.utc)
        self._path_for(job_id).write_text(json.dumps(record.to_dict(), indent=2))
        return record

    def _path_for(self, job_id: str) -> Path:
        return self._root / f"{job_id}.json"
