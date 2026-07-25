from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

from .approval import ApprovalStatus, IApprovalStore
from .errors import ApprovalRequiredError, BudgetExceededError


@dataclass(frozen=True)
class UsageRecord:
    """One real, incurred charge - recorded *after* a paid job completes
    and its actual provider-billed cost is known, not at estimate time.
    `period_key` (e.g. "2026-07") is what total_spent_in_period() groups
    on, so budgets reset monthly without needing a scheduled job to
    "clear" anything."""

    job_id: str
    provider: str
    amount_usd: float
    incurred_at: datetime
    period_key: str

    def to_dict(self) -> dict:
        data = asdict(self)
        data["incurred_at"] = self.incurred_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "UsageRecord":
        return cls(
            job_id=data["job_id"],
            provider=data["provider"],
            amount_usd=data["amount_usd"],
            incurred_at=datetime.fromisoformat(data["incurred_at"]),
            period_key=data["period_key"],
        )

    @staticmethod
    def current_period_key(at: datetime | None = None) -> str:
        moment = at or datetime.now(timezone.utc)
        return f"{moment.year:04d}-{moment.month:02d}"


class IUsageLedger(ABC):
    @abstractmethod
    def record(self, usage: UsageRecord) -> None: ...

    @abstractmethod
    def total_spent_in_period(self, period_key: str) -> float: ...

    @abstractmethod
    def all_records(self) -> list[UsageRecord]: ...


class InMemoryUsageLedger(IUsageLedger):
    def __init__(self) -> None:
        self._records: list[UsageRecord] = []

    def record(self, usage: UsageRecord) -> None:
        self._records.append(usage)

    def total_spent_in_period(self, period_key: str) -> float:
        return sum(r.amount_usd for r in self._records if r.period_key == period_key)

    def all_records(self) -> list[UsageRecord]:
        return list(self._records)


class FilesystemUsageLedger(IUsageLedger):
    """Append-only JSON-lines file under `root_dir/usage.jsonl` - simple,
    diffable, and safe to check into the same repo/artifact storage the
    rest of services/training already uses for checkpoints and registry
    records."""

    def __init__(self, root_dir: Path) -> None:
        self._root = root_dir
        self._root.mkdir(parents=True, exist_ok=True)
        self._path = self._root / "usage.jsonl"

    def record(self, usage: UsageRecord) -> None:
        with self._path.open("a") as f:
            f.write(json.dumps(usage.to_dict()) + "\n")

    def total_spent_in_period(self, period_key: str) -> float:
        return sum(r.amount_usd for r in self.all_records() if r.period_key == period_key)

    def all_records(self) -> list[UsageRecord]:
        if not self._path.exists():
            return []
        with self._path.open() as f:
            return [UsageRecord.from_dict(json.loads(line)) for line in f if line.strip()]


class CostGuard:
    """The single choke point every paid-GPU dispatch path must call
    before touching RunPod/Vast.ai/fal.ai. Encodes exactly the two rules
    from the training-factory architecture report's cost-protection
    section: (1) never start a paid job without a human APPROVED record
    for that specific job_id, at or under the human-approved cost
    ceiling, and (2) never let a job push total spend for the current
    period over `monthly_budget_usd`, regardless of approval."""

    def __init__(
        self,
        *,
        approval_store: IApprovalStore,
        usage_ledger: IUsageLedger,
        monthly_budget_usd: float,
    ) -> None:
        if monthly_budget_usd <= 0:
            raise ValueError("monthly_budget_usd must be positive")
        self._approvals = approval_store
        self._usage = usage_ledger
        self._monthly_budget_usd = monthly_budget_usd

    def authorize_paid_job(self, job_id: str, estimated_cost_usd: float) -> None:
        record = self._approvals.get(job_id)
        if record is None or record.status != ApprovalStatus.APPROVED:
            status = record.status.value if record else "no request found"
            raise ApprovalRequiredError(
                f"job_id={job_id!r} is not approved for paid GPU dispatch (status: {status}). "
                "A human must approve this specific job via the paid-GPU approval gate first."
            )
        if estimated_cost_usd > record.max_cost_usd:
            raise ApprovalRequiredError(
                f"job_id={job_id!r} estimated cost ${estimated_cost_usd:.2f} exceeds the "
                f"${record.max_cost_usd:.2f} ceiling the human approval covered - re-approval required."
            )

        period_key = UsageRecord.current_period_key()
        spent = self._usage.total_spent_in_period(period_key)
        if spent + estimated_cost_usd > self._monthly_budget_usd:
            raise BudgetExceededError(
                f"job_id={job_id!r} estimated cost ${estimated_cost_usd:.2f} would push "
                f"{period_key} spend to ${spent + estimated_cost_usd:.2f}, over the "
                f"${self._monthly_budget_usd:.2f} monthly budget (${spent:.2f} already spent)."
            )

    def record_actual_spend(self, job_id: str, *, provider: str, amount_usd: float) -> None:
        self._usage.record(
            UsageRecord(
                job_id=job_id,
                provider=provider,
                amount_usd=amount_usd,
                incurred_at=datetime.now(timezone.utc),
                period_key=UsageRecord.current_period_key(),
            )
        )

    def remaining_budget_usd(self) -> float:
        spent = self._usage.total_spent_in_period(UsageRecord.current_period_key())
        return self._monthly_budget_usd - spent
