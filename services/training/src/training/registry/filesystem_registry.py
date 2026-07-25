from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .compatibility import validate_capability_manifest
from .interfaces import IModelRegistry, ModelRegistryError, UnknownModelVersionError
from .records import ModelVersionRecord, PromotionStatus, assert_valid_transition


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class FilesystemModelRegistry(IModelRegistry):
    """Real, disk-backed `IModelRegistry`: one JSON file per version
    under `root_dir/versions/`, plus a small append-only
    `production_history.json` recording the order versions held
    PRODUCTION - what `rollback()` reads to know what to revert to.
    Genuinely persists across process restarts; no GPU, model weights,
    or network access needed, since a `ModelVersionRecord` only ever
    holds metadata pointing at a checkpoint, never the weights
    themselves.

    Promoting to CANARY or PRODUCTION runs
    `registry.compatibility.validate_capability_manifest` first and
    refuses on any structural error - a promotion is exactly the moment
    a version starts being taken seriously as a real deployment
    candidate, so this is where the gate belongs, not at `register()`
    time (an experimental STAGING checkpoint may have a rough manifest
    that's still fine to keep around for comparison).

    `rollback()` sets the prior version directly back to PRODUCTION,
    bypassing the normal ARCHIVED -> CANARY -> PRODUCTION path
    `registry.records.assert_valid_transition` otherwise enforces - a
    documented, deliberate exception: the entire point of rollback is an
    instant revert to a version that was already proven in production
    before, not a re-run of the promotion ladder under time pressure.
    """

    def __init__(self, root_dir: str | Path) -> None:
        self._root = Path(root_dir)
        self._versions_dir = self._root / "versions"
        self._versions_dir.mkdir(parents=True, exist_ok=True)
        self._history_path = self._root / "production_history.json"

    def _path(self, version_id: str) -> Path:
        return self._versions_dir / f"{version_id}.json"

    def _save(self, record: ModelVersionRecord) -> None:
        self._path(record.version_id).write_text(json.dumps(record.to_dict(), indent=2))

    def register(self, record: ModelVersionRecord) -> None:
        if self._path(record.version_id).exists():
            raise ModelRegistryError(f"Model version {record.version_id!r} is already registered")
        self._save(record)

    def get(self, version_id: str) -> ModelVersionRecord | None:
        path = self._path(version_id)
        if not path.exists():
            return None
        return ModelVersionRecord.from_dict(json.loads(path.read_text()))

    def list_all(self) -> list[ModelVersionRecord]:
        records = [
            ModelVersionRecord.from_dict(json.loads(p.read_text())) for p in self._versions_dir.glob("*.json")
        ]
        return sorted(records, key=lambda r: r.created_at)

    def _require(self, version_id: str) -> ModelVersionRecord:
        record = self.get(version_id)
        if record is None:
            raise UnknownModelVersionError(f"No such model version: {version_id!r}")
        return record

    def promote(self, version_id: str, target_status: PromotionStatus) -> ModelVersionRecord:
        record = self._require(version_id)
        assert_valid_transition(record.status, target_status)

        if target_status in (PromotionStatus.CANARY, PromotionStatus.PRODUCTION):
            result = validate_capability_manifest(record.capability_manifest)
            if not result.valid:
                errors = [issue.message for issue in result.issues if issue.severity == "error"]
                raise ModelRegistryError(
                    f"Cannot promote {version_id!r} to {target_status.value!r}: capability manifest "
                    f"failed compatibility validation: {errors}"
                )

        if target_status == PromotionStatus.PRODUCTION:
            previous_production = self.get_production()
            if previous_production is not None and previous_production.version_id != version_id:
                previous_production.status = PromotionStatus.ARCHIVED
                previous_production.updated_at = _now()
                self._save(previous_production)
            history = self._load_history()
            history.append(version_id)
            self._save_history(history)

        record.status = target_status
        record.updated_at = _now()
        self._save(record)
        return record

    def get_production(self) -> ModelVersionRecord | None:
        for record in self.list_all():
            if record.status == PromotionStatus.PRODUCTION:
                return record
        return None

    def rollback(self) -> ModelVersionRecord | None:
        history = self._load_history()
        if len(history) < 2:
            return None

        current = self._require(history[-1])
        current.status = PromotionStatus.ARCHIVED
        current.updated_at = _now()
        self._save(current)

        previous = self._require(history[-2])
        previous.status = PromotionStatus.PRODUCTION
        previous.updated_at = _now()
        self._save(previous)

        history.pop()
        self._save_history(history)
        return previous

    def _load_history(self) -> list[str]:
        if not self._history_path.exists():
            return []
        return json.loads(self._history_path.read_text())

    def _save_history(self, history: list[str]) -> None:
        self._history_path.write_text(json.dumps(history, indent=2))
