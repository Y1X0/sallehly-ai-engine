from __future__ import annotations

from typing import Any

import schemas

from ._util import new_id, now_iso

# Fields on the embedded StyleSetup (style.schema.json, via
# StyleLock.base_style) that are load-bearing for "does this shot match
# the locked look" - checked field-by-field by check_drift().
_DRIFT_SENSITIVE_STYLE_FIELDS = ("visual_style",)


class StyleLockEngineError(Exception):
    """Raised when a caller tries to re-lock a project that already has a
    StyleLock, looks up one that doesn't exist, or an assembled
    StyleLock fails schema validation."""


class StyleLockEngine:
    """Creates and enforces the single global StyleLock
    (style_lock.schema.json) for a project - grading, contrast, film
    stock, grain, color palette, lighting language, depth of field,
    bloom, and lens effects, locked once via `lock()` and never mutated
    in place (same immutability discipline as CharacterIdentityProfile).
    `check_drift()` is how a shot's proposed style_override
    (shot.schema.json) gets checked against the lock before it's allowed
    to reach a RenderSpec, so no scene can drift stylistically from the
    rest of the film."""

    def __init__(self) -> None:
        self._locks: dict[str, dict[str, Any]] = {}  # keyed by project_id

    def lock(
        self,
        project_id: str,
        base_style: dict[str, Any],
        *,
        style_lock_id: str | None = None,
        film_stock: str | None = None,
        grain: dict[str, Any] | None = None,
        depth_of_field_target: str = "medium",
        bloom: dict[str, Any] | None = None,
        lens_effects: list[str] | None = None,
        lighting_language: str | None = None,
    ) -> dict[str, Any]:
        if project_id in self._locks:
            raise StyleLockEngineError(
                f"Project {project_id} already has a StyleLock - a deliberate "
                "style change requires a new project (or, in a future phase, "
                "explicit re-lock tooling), never an in-place edit"
            )

        lock: dict[str, Any] = {
            "schema_version": "1.0",
            "style_lock_id": style_lock_id or new_id("style"),
            "project_id": project_id,
            "base_style": base_style,
            "depth_of_field_target": depth_of_field_target,
            "locked": True,
            "created_at": now_iso(),
        }
        if film_stock:
            lock["film_stock"] = film_stock
        if grain:
            lock["grain"] = grain
        if bloom:
            lock["bloom"] = bloom
        if lens_effects:
            lock["lens_effects"] = lens_effects
        if lighting_language:
            lock["lighting_language"] = lighting_language

        try:
            schemas.validate(lock, "style_lock")
        except Exception as exc:  # noqa: BLE001
            raise StyleLockEngineError(f"Assembled StyleLock failed validation: {exc}") from exc

        self._locks[project_id] = lock
        return lock

    def get(self, project_id: str) -> dict[str, Any]:
        try:
            return self._locks[project_id]
        except KeyError:
            raise StyleLockEngineError(f"No StyleLock for project {project_id!r} - call lock() first") from None

    def exists(self, project_id: str) -> bool:
        return project_id in self._locks

    def check_drift(self, project_id: str, shot_style_override: dict[str, Any]) -> list[dict[str, Any]]:
        """Compares a shot's style_override (style.schema.json) against
        the locked base_style, field by field, without mutating
        anything. Returns ContinuityViolation-shaped dicts
        (violation_type='style_drift') for every field that disagrees."""
        base_style = self.get(project_id)["base_style"]
        violations: list[dict[str, Any]] = []
        for field_name in _DRIFT_SENSITIVE_STYLE_FIELDS:
            locked_value = base_style.get(field_name)
            proposed_value = shot_style_override.get(field_name)
            if locked_value is not None and proposed_value is not None and proposed_value != locked_value:
                violations.append(
                    {
                        "violation_type": "style_drift",
                        "severity": "warning",
                        "description": (
                            f"{field_name} overridden to {proposed_value!r}, "
                            f"diverging from the locked {locked_value!r}"
                        ),
                    }
                )

        locked_palette = set((base_style.get("color_grade") or {}).get("palette") or [])
        proposed_palette = set((shot_style_override.get("color_grade") or {}).get("palette") or [])
        if locked_palette and proposed_palette and not proposed_palette & locked_palette:
            violations.append(
                {
                    "violation_type": "style_drift",
                    "severity": "warning",
                    "description": (
                        f"color_grade.palette {sorted(proposed_palette)} shares no colors "
                        f"with the locked palette {sorted(locked_palette)}"
                    ),
                }
            )
        return violations
