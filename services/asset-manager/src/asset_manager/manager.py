from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import schemas
from storage_sdk import IStorageProvider


class AssetManager:
    """Registry for generated/uploaded assets (video clips, preview
    images, metadata blobs), with simple per-key versioning.

    Phase 3 scope: record *where* an asset already lives (a RawClip's
    storage_uri, wherever IComputeProvider/IVideoEngine put it) and track
    its version history - this class does not move bytes around itself.
    An optional IStorageProvider can be attached for the cases where the
    platform does need to copy/persist bytes (see packages/storage-sdk);
    it is not required for the core registration flow.
    """

    def __init__(self, storage: IStorageProvider | None = None) -> None:
        self._storage = storage
        self._assets: dict[str, dict[str, Any]] = {}  # f"{project}:{shot}:{kind}" -> AssetRecord

    def register_video(self, project_id: str, shot_id: str, raw_clip: Any) -> dict[str, Any]:
        """Convenience for the common case: register a RawClip
        (video_engine_sdk.types.RawClip) as this shot's video asset."""
        return self.register(
            project_id=project_id,
            shot_id=shot_id,
            kind="video",
            uri=raw_clip.storage_uri,
            metadata=dict(raw_clip.engine_metadata),
        )

    def register(
        self,
        project_id: str,
        kind: str,
        uri: str,
        shot_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        asset_key = f"{project_id}:{shot_id or '_project'}:{kind}"
        existing = self._assets.get(asset_key)
        next_version = existing["versions"][-1]["version"] + 1 if existing else 1

        version_entry = {
            "version": next_version,
            "uri": uri,
            "created_at": _now(),
            "metadata": metadata or {},
        }

        if existing:
            existing["versions"].append(version_entry)
            record = existing
        else:
            record = {
                "schema_version": "1.0",
                "asset_id": f"asset_{uuid.uuid4().hex[:12]}",
                "project_id": project_id,
                "kind": kind,
                "versions": [version_entry],
            }
            if shot_id is not None:
                record["shot_id"] = shot_id
            self._assets[asset_key] = record

        schemas.validate(record, "asset_record")
        return record

    def get(self, asset_id: str) -> dict[str, Any] | None:
        return next((record for record in self._assets.values() if record["asset_id"] == asset_id), None)

    def list_for_project(self, project_id: str, kind: str | None = None) -> list[dict[str, Any]]:
        """Every AssetRecord for a project, optionally filtered by kind -
        e.g. `list_for_project(project_id, kind="video")` to gather a
        project's per-shot clips for Post-Processing's TimelineBuilder."""
        return [
            record
            for record in self._assets.values()
            if record["project_id"] == project_id and (kind is None or record["kind"] == kind)
        ]

    def latest_uri(self, project_id: str, kind: str, shot_id: str | None = None) -> str | None:
        record = self._assets.get(f"{project_id}:{shot_id or '_project'}:{kind}")
        return record["versions"][-1]["uri"] if record else None

    def persist_local_copy(self, key: str, source_path: str) -> str:
        """Copies a local file into the attached IStorageProvider and
        returns its URI. Raises if no provider was configured."""
        if self._storage is None:
            raise RuntimeError("AssetManager has no IStorageProvider configured")
        return self._storage.put(key, source_path)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
