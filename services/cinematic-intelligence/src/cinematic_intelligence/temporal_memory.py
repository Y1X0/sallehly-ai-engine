from __future__ import annotations

from typing import Any

import schemas

from ._util import new_id, now_iso


class TemporalMemoryEngineError(Exception):
    """Raised when an assembled ProjectMemory fails schema validation."""


class TemporalMemoryEngine:
    """Maintains one ProjectMemory (project_memory.schema.json) per
    project, updated after every generated shot via `record_shot()`.
    Every other Phase 7 engine that needs "what has this project already
    established" (Prompt Intelligence Engine building the next shot's
    context, Continuity Engines comparing against what came before)
    reads from here instead of a caller having to pass the full project
    history by hand on every call - no LLM or engine in this system is
    meant to rely on the current shot's prompt alone. See
    docs/adr/0013-cinematic-intelligence-layer.md."""

    def __init__(self) -> None:
        self._memories: dict[str, dict[str, Any]] = {}

    def get_or_create(self, project_id: str) -> dict[str, Any]:
        if project_id not in self._memories:
            memory: dict[str, Any] = {
                "schema_version": "1.0",
                "project_id": project_id,
                "character_ids": [],
                "object_ids": [],
                "environment_ids": [],
                "events": [],
                "timeline": [],
                "updated_at": now_iso(),
            }
            self._validate(memory)
            self._memories[project_id] = memory
        return self._memories[project_id]

    def register_character(self, project_id: str, character_id: str) -> dict[str, Any]:
        return self._append_unique(project_id, "character_ids", character_id)

    def register_object(self, project_id: str, object_id: str) -> dict[str, Any]:
        return self._append_unique(project_id, "object_ids", object_id)

    def register_environment(self, project_id: str, environment_id: str) -> dict[str, Any]:
        return self._append_unique(project_id, "environment_ids", environment_id)

    def set_style_lock(self, project_id: str, style_lock_id: str) -> dict[str, Any]:
        memory = {**self.get_or_create(project_id), "style_lock_id": style_lock_id}
        self._save(memory)
        return memory

    def record_shot(
        self,
        project_id: str,
        shot_id: str,
        scene_id: str,
        summary: str,
        *,
        character_ids: list[str] | None = None,
        object_ids: list[str] | None = None,
        environment_id: str | None = None,
        camera: dict[str, Any] | None = None,
        order: int | None = None,
    ) -> dict[str, Any]:
        memory = self.get_or_create(project_id)
        character_ids = character_ids or []
        object_ids = object_ids or []

        event: dict[str, Any] = {
            "event_id": new_id("evt"),
            "shot_id": shot_id,
            "scene_id": scene_id,
            "summary": summary,
        }
        if character_ids:
            event["character_ids"] = character_ids
        if object_ids:
            event["object_ids"] = object_ids
        if environment_id:
            event["environment_id"] = environment_id
        if order is not None:
            event["order"] = order

        resolved_order = order if order is not None else len(memory["timeline"])
        timeline_entry = {
            "shot_id": shot_id,
            "scene_id": scene_id,
            "order": resolved_order,
            "summary": summary,
        }

        memory = {
            **memory,
            "events": [*memory["events"], event],
            "timeline": [*memory["timeline"], timeline_entry],
            "character_ids": _merge_unique(memory["character_ids"], character_ids),
            "object_ids": _merge_unique(memory["object_ids"], object_ids),
            "environment_ids": _merge_unique(
                memory["environment_ids"], [environment_id] if environment_id else []
            ),
        }
        if camera is not None:
            memory["last_camera_state"] = {"shot_id": shot_id, "camera": camera}

        self._save(memory)
        return memory

    def _append_unique(self, project_id: str, field_name: str, value: str) -> dict[str, Any]:
        memory = self.get_or_create(project_id)
        if value in memory[field_name]:
            return memory
        memory = {**memory, field_name: [*memory[field_name], value]}
        self._save(memory)
        return memory

    def _save(self, memory: dict[str, Any]) -> None:
        memory = {**memory, "updated_at": now_iso()}
        self._validate(memory)
        self._memories[memory["project_id"]] = memory

    def _validate(self, memory: dict[str, Any]) -> None:
        try:
            schemas.validate(memory, "project_memory")
        except Exception as exc:  # noqa: BLE001
            raise TemporalMemoryEngineError(f"Assembled ProjectMemory failed validation: {exc}") from exc


def _merge_unique(existing: list[str], new_values: list[str]) -> list[str]:
    merged = list(existing)
    for value in new_values:
        if value not in merged:
            merged.append(value)
    return merged
