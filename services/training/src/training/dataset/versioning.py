from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .records import ClipRecord
from .statistics import DatasetStatistics, compute_statistics


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def compute_version_id(records: list[ClipRecord]) -> str:
    """Content-addressable, not a manually incremented label: the same
    set of clips (identified by `clip_id:file_hash` pairs, sorted for
    order-independence) always produces the same version id, so a
    `TrainingConfig.dataset_version` string can be trusted to mean
    "exactly this data" rather than relying on someone remembering to
    bump a counter when the underlying clip set changes."""
    digest = hashlib.sha256()
    for record in sorted(records, key=lambda r: r.clip_id):
        digest.update(f"{record.clip_id}:{record.metadata.file_hash}".encode())
    return digest.hexdigest()[:16]


@dataclass(frozen=True)
class DatasetVersion:
    """One immutable snapshot of a dataset - which clips it contains
    (`clip_ids`) and what it looked like statistically at that moment.
    Mirrors `checkpoint.CheckpointRecord`'s and
    `registry.records.ModelVersionRecord`'s "content is immutable, only
    the record around it changes" shape."""

    version_id: str
    clip_ids: tuple[str, ...]
    statistics: DatasetStatistics
    created_at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version_id": self.version_id,
            "clip_ids": list(self.clip_ids),
            "statistics": self.statistics.to_dict(),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DatasetVersion":
        return cls(
            version_id=data["version_id"],
            clip_ids=tuple(data["clip_ids"]),
            statistics=DatasetStatistics(**data["statistics"]),
            created_at=data["created_at"],
        )


def build_dataset_version(records: list[ClipRecord]) -> DatasetVersion:
    return DatasetVersion(
        version_id=compute_version_id(records),
        clip_ids=tuple(sorted(r.clip_id for r in records)),
        statistics=compute_statistics(records),
    )


class IDatasetVersionStore(ABC):
    """Persists `DatasetVersion` snapshots - same create/get/list shape
    as every other store in this codebase (`IProjectStore`,
    `ICheckpointStore`)."""

    @abstractmethod
    def save(self, version: DatasetVersion) -> None: ...

    @abstractmethod
    def get(self, version_id: str) -> DatasetVersion | None: ...

    @abstractmethod
    def list_all(self) -> list[DatasetVersion]: ...


class FilesystemDatasetVersionStore(IDatasetVersionStore):
    """Real, disk-backed `IDatasetVersionStore`: one JSON file per
    version under `root_dir`. Genuinely persists across process
    restarts - no GPU or model access needed, since a `DatasetVersion`
    is just clip ids and statistics, never the clip bytes themselves."""

    def __init__(self, root_dir: str | Path) -> None:
        self._root = Path(root_dir)
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, version_id: str) -> Path:
        return self._root / f"{version_id}.json"

    def save(self, version: DatasetVersion) -> None:
        self._path(version.version_id).write_text(json.dumps(version.to_dict(), indent=2))

    def get(self, version_id: str) -> DatasetVersion | None:
        path = self._path(version_id)
        if not path.exists():
            return None
        return DatasetVersion.from_dict(json.loads(path.read_text()))

    def list_all(self) -> list[DatasetVersion]:
        versions = [DatasetVersion.from_dict(json.loads(p.read_text())) for p in self._root.glob("*.json")]
        return sorted(versions, key=lambda v: v.created_at)
