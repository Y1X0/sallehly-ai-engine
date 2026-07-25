from __future__ import annotations

import json
import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class CheckpointRecord:
    """Metadata for one saved training checkpoint - deliberately
    separate from `registry.records.ModelVersionRecord` (services/training/
    src/training/registry): a checkpoint is an artifact a *training run*
    produces at some step; a model version is a *promotable* entry the
    Model Registry tracks, usually pointing at exactly one checkpoint
    (typically the final/best one) once someone decides it's worth
    evaluating for promotion. Every training run can produce many
    checkpoints; not every checkpoint becomes a model version.
    """

    checkpoint_id: str
    run_id: str
    step: int
    artifact_uri: str
    """Where the actual weights would live - a `file://` path in this
    dry-run-only environment, an `s3://` URI once storage_sdk.S3Provider
    (already real, Phase 8 WP4) is pointed at a real training job."""
    size_bytes: int
    metrics: dict[str, float] = field(default_factory=dict)
    created_at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "run_id": self.run_id,
            "step": self.step,
            "artifact_uri": self.artifact_uri,
            "size_bytes": self.size_bytes,
            "metrics": self.metrics,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CheckpointRecord":
        return cls(
            checkpoint_id=data["checkpoint_id"],
            run_id=data["run_id"],
            step=data["step"],
            artifact_uri=data["artifact_uri"],
            size_bytes=data["size_bytes"],
            metrics=dict(data.get("metrics") or {}),
            created_at=data["created_at"],
        )


class ICheckpointStore(ABC):
    """Where training checkpoints are recorded and retrieved. Named
    deliberately parallel to `IProjectStore`/`IGenerationJobStore`
    (packages/persistence, services/render-orchestrator) - same
    create/get/list shape, so anyone already familiar with this
    codebase's persistence pattern needs to learn nothing new here."""

    @abstractmethod
    def save(self, record: CheckpointRecord) -> None: ...

    @abstractmethod
    def get(self, checkpoint_id: str) -> CheckpointRecord | None: ...

    @abstractmethod
    def list_for_run(self, run_id: str) -> list[CheckpointRecord]: ...

    @abstractmethod
    def delete(self, checkpoint_id: str) -> None: ...


class InMemoryCheckpointStore(ICheckpointStore):
    """Process-local - for tests and any dry-run trainer session that
    doesn't need its checkpoint index to outlive the process."""

    def __init__(self) -> None:
        self._checkpoints: dict[str, CheckpointRecord] = {}

    def save(self, record: CheckpointRecord) -> None:
        self._checkpoints[record.checkpoint_id] = record

    def get(self, checkpoint_id: str) -> CheckpointRecord | None:
        return self._checkpoints.get(checkpoint_id)

    def list_for_run(self, run_id: str) -> list[CheckpointRecord]:
        return sorted(
            (r for r in self._checkpoints.values() if r.run_id == run_id),
            key=lambda r: r.step,
        )

    def delete(self, checkpoint_id: str) -> None:
        self._checkpoints.pop(checkpoint_id, None)


class FilesystemCheckpointStore(ICheckpointStore):
    """Real, disk-backed `ICheckpointStore`: one JSON file per checkpoint
    under `root_dir`. Genuinely persists across process restarts - no
    GPU, model weights, or network access needed to exercise this, since
    it only ever manages the *metadata record*, never the (currently
    nonexistent) weight file itself. Mirrors the JSON-file-per-record
    pattern already established for local dev artifacts elsewhere in
    this codebase (e.g. `video_engine_adapter.compute.LocalProvider`'s
    stub job files)."""

    def __init__(self, root_dir: str | Path) -> None:
        self._root = Path(root_dir)
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, checkpoint_id: str) -> Path:
        return self._root / f"{checkpoint_id}.json"

    def save(self, record: CheckpointRecord) -> None:
        self._path(record.checkpoint_id).write_text(json.dumps(record.to_dict(), indent=2))

    def get(self, checkpoint_id: str) -> CheckpointRecord | None:
        path = self._path(checkpoint_id)
        if not path.exists():
            return None
        return CheckpointRecord.from_dict(json.loads(path.read_text()))

    def list_for_run(self, run_id: str) -> list[CheckpointRecord]:
        records = []
        for path in self._root.glob("*.json"):
            record = CheckpointRecord.from_dict(json.loads(path.read_text()))
            if record.run_id == run_id:
                records.append(record)
        return sorted(records, key=lambda r: r.step)

    def delete(self, checkpoint_id: str) -> None:
        self._path(checkpoint_id).unlink(missing_ok=True)

    def purge_run(self, run_id: str) -> None:
        """Not part of `ICheckpointStore` - a filesystem-specific
        convenience for tests to clean up after themselves without
        depending on the retention policy Stage 11 of the Phase 9
        roadmap (docs/adr/0021-phase9-preparation.md) still needs to
        define for production."""
        for record in self.list_for_run(run_id):
            self.delete(record.checkpoint_id)
