from __future__ import annotations

from typing import Any

import schemas

from ._util import new_id, now_iso


class ObjectConsistencyEngineError(Exception):
    """Raised when a caller looks up an object_id that was never
    established, or an assembled ObjectProfile fails schema validation."""


class ObjectConsistencyEngine:
    """Creates and tracks ObjectProfiles (object_profile.schema.json) for
    every persistent, narratively significant object (a car, a phone, a
    hammer, a chair, a door, a pet, a tree, ...) so its materials/colors/
    damage state never contradict themselves between shots, and its
    location history never implies it teleported. Unlike
    CharacterIdentityProfile, an ObjectProfile is allowed to evolve
    (`record_location`, `update_damage_state`) - an object's *identity*
    (name, materials, colors) stays fixed once established, but its
    *state* (where it is, how damaged it is) is expected to change
    across a story."""

    def __init__(self) -> None:
        self._profiles: dict[str, dict[str, Any]] = {}

    def establish(
        self,
        project_id: str,
        name: str,
        *,
        object_id: str | None = None,
        attributes: dict[str, Any] | None = None,
        reference_image_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        object_id = object_id or new_id("obj")
        if object_id in self._profiles:
            raise ObjectConsistencyEngineError(
                f"ObjectProfile {object_id} already exists - reuse it via get()"
            )

        profile: dict[str, Any] = {
            "schema_version": "1.0",
            "object_id": object_id,
            "project_id": project_id,
            "name": name,
            "attributes": attributes or {"damage_state": "pristine"},
            "created_at": now_iso(),
        }
        if reference_image_ids:
            profile["reference_image_ids"] = reference_image_ids

        self._validate(profile)
        self._profiles[object_id] = profile
        return profile

    def get(self, object_id: str) -> dict[str, Any]:
        try:
            return self._profiles[object_id]
        except KeyError:
            raise ObjectConsistencyEngineError(
                f"No ObjectProfile for object_id {object_id!r} - it must be "
                "established before it can be reused"
            ) from None

    def record_location(self, object_id: str, scene_id: str, shot_id: str, location: str) -> dict[str, Any]:
        """Appends to location_history - the record a Scene Continuity
        Engine cross-checks a later shot's claimed object location
        against, to catch an object appearing somewhere it never moved
        to (violation_type='object_location_conflict')."""
        profile = self.get(object_id)
        history = list(profile.get("location_history", []))
        history.append({"scene_id": scene_id, "shot_id": shot_id, "location": location})
        profile = {**profile, "location_history": history}
        self._validate(profile)
        self._profiles[object_id] = profile
        return profile

    def update_damage_state(self, object_id: str, damage_state: str) -> dict[str, Any]:
        profile = self.get(object_id)
        attributes = {**profile.get("attributes", {}), "damage_state": damage_state}
        profile = {**profile, "attributes": attributes}
        self._validate(profile)
        self._profiles[object_id] = profile
        return profile

    def exists(self, object_id: str) -> bool:
        return object_id in self._profiles

    def current_location(self, object_id: str) -> str | None:
        history = self.get(object_id).get("location_history", [])
        return history[-1]["location"] if history else None

    def list_for_project(self, project_id: str) -> list[dict[str, Any]]:
        return [p for p in self._profiles.values() if p["project_id"] == project_id]

    def _validate(self, profile: dict[str, Any]) -> None:
        try:
            schemas.validate(profile, "object_profile")
        except Exception as exc:  # noqa: BLE001
            raise ObjectConsistencyEngineError(f"Assembled ObjectProfile failed validation: {exc}") from exc
