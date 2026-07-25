from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class HumanEvalRecord:
    """One reviewer's rating of one benchmark case's output - the
    non-automatable half of Stage 7's evaluation pipeline
    (docs/adr/0021-phase9-preparation.md): automated metrics catch
    conformance and gross failures, but "does this actually look
    cinematic" still needs a human until a real perceptual-quality model
    exists. `rating` is a 1-5 Likert scale, matching the vocabulary a
    non-technical creative reviewer would already use, not an internal
    0-1 score."""

    record_id: str
    version_id: str
    case_id: str
    reviewer_id: str
    rating: int
    notes: str = ""
    created_at: str = field(default_factory=_now)

    def validate(self) -> None:
        if not (1 <= self.rating <= 5):
            raise ValueError(f"HumanEvalRecord.rating must be in [1, 5], got {self.rating}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "version_id": self.version_id,
            "case_id": self.case_id,
            "reviewer_id": self.reviewer_id,
            "rating": self.rating,
            "notes": self.notes,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HumanEvalRecord":
        return cls(
            record_id=data["record_id"],
            version_id=data["version_id"],
            case_id=data["case_id"],
            reviewer_id=data["reviewer_id"],
            rating=data["rating"],
            notes=data.get("notes", ""),
            created_at=data["created_at"],
        )


class IHumanEvalStore(ABC):
    @abstractmethod
    def save(self, record: HumanEvalRecord) -> None: ...

    @abstractmethod
    def list_for_version(self, version_id: str) -> list[HumanEvalRecord]: ...


class InMemoryHumanEvalStore(IHumanEvalStore):
    def __init__(self) -> None:
        self._records: dict[str, HumanEvalRecord] = {}

    def save(self, record: HumanEvalRecord) -> None:
        record.validate()
        self._records[record.record_id] = record

    def list_for_version(self, version_id: str) -> list[HumanEvalRecord]:
        return [r for r in self._records.values() if r.version_id == version_id]


def mean_rating(records: list[HumanEvalRecord]) -> float | None:
    if not records:
        return None
    return round(sum(r.rating for r in records) / len(records), 3)
