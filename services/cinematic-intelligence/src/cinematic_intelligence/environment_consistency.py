from __future__ import annotations

from typing import Any

import schemas

from ._util import new_id, now_iso

# Fields a deliberate `update()` call is allowed to change. Anything else
# in an EnvironmentProfile (name, environment_id, project_id,
# first_established_scene_id) is fixed at establish() time.
_MUTABLE_FIELDS = {
    "weather",
    "time_of_day",
    "season",
    "architecture",
    "layout",
    "sky",
    "fog",
    "camera_geography_notes",
    "reference_image_ids",
}

# Fields whose value changing without an explicit narrative reason is
# exactly the "impossible jump" this engine exists to catch (a sunny
# street becoming a blizzard one shot later, interior daylight suddenly
# reading as night, ...).
_CONTINUITY_SENSITIVE_FIELDS = ("weather", "time_of_day", "season", "sky")


class EnvironmentConsistencyEngineError(Exception):
    """Raised when a caller looks up an environment_id that was never
    established, tries to mutate a fixed field via update(), or an
    assembled EnvironmentProfile fails schema validation."""


class EnvironmentConsistencyEngine:
    """Creates and tracks EnvironmentProfiles
    (environment_profile.schema.json) for every persistent location a
    project's scenes are set in, so weather/time-of-day/architecture/
    layout/season/sky/fog/geography stay coherent across every scene set
    there. `update()` is how a *deliberate* environment change (dusk
    turning to night, a storm rolling in) is recorded; `detect_drift()`
    is how an *accidental* one gets caught before it ever reaches
    `update()` - the Scene Continuity Engine calls it when comparing two
    shots that both claim to use the same environment_id."""

    def __init__(self) -> None:
        self._profiles: dict[str, dict[str, Any]] = {}

    def establish(
        self,
        project_id: str,
        name: str,
        *,
        environment_id: str | None = None,
        weather: str | None = None,
        time_of_day: str | None = None,
        season: str | None = None,
        architecture: str | None = None,
        layout: str | None = None,
        sky: str | None = None,
        fog: bool = False,
        camera_geography_notes: str | None = None,
        reference_image_ids: list[str] | None = None,
        first_established_scene_id: str | None = None,
    ) -> dict[str, Any]:
        environment_id = environment_id or new_id("env")
        if environment_id in self._profiles:
            raise EnvironmentConsistencyEngineError(
                f"EnvironmentProfile {environment_id} already exists - reuse it via get()"
            )

        profile: dict[str, Any] = {
            "schema_version": "1.0",
            "environment_id": environment_id,
            "project_id": project_id,
            "name": name,
            "fog": fog,
            "created_at": now_iso(),
        }
        for key, value in {
            "weather": weather,
            "time_of_day": time_of_day,
            "season": season,
            "architecture": architecture,
            "layout": layout,
            "sky": sky,
            "camera_geography_notes": camera_geography_notes,
            "first_established_scene_id": first_established_scene_id,
        }.items():
            if value is not None:
                profile[key] = value
        if reference_image_ids:
            profile["reference_image_ids"] = reference_image_ids

        self._validate(profile)
        self._profiles[environment_id] = profile
        return profile

    def get(self, environment_id: str) -> dict[str, Any]:
        try:
            return self._profiles[environment_id]
        except KeyError:
            raise EnvironmentConsistencyEngineError(
                f"No EnvironmentProfile for environment_id {environment_id!r} - "
                "it must be established before it can be reused"
            ) from None

    def exists(self, environment_id: str) -> bool:
        return environment_id in self._profiles

    def update(self, environment_id: str, **changes: Any) -> dict[str, Any]:
        unknown = set(changes) - _MUTABLE_FIELDS
        if unknown:
            raise EnvironmentConsistencyEngineError(
                f"update() cannot change fixed fields: {sorted(unknown)}"
            )
        profile = {**self.get(environment_id), **changes}
        self._validate(profile)
        self._profiles[environment_id] = profile
        return profile

    def detect_drift(self, environment_id: str, proposed_state: dict[str, Any]) -> list[dict[str, str]]:
        """Compares `proposed_state` (a partial dict of the same
        continuity-sensitive fields) against the currently established
        profile without mutating anything. Returns a list of
        ContinuityViolation-shaped dicts (violation_type='environment_jump')
        for every field that disagrees - empty if everything matches."""
        current = self.get(environment_id)
        violations: list[dict[str, str]] = []
        for field_name in _CONTINUITY_SENSITIVE_FIELDS:
            if field_name not in proposed_state:
                continue
            current_value = current.get(field_name)
            proposed_value = proposed_state[field_name]
            if current_value is not None and proposed_value != current_value:
                violations.append(
                    {
                        "violation_type": "environment_jump",
                        "severity": "critical",
                        "description": (
                            f"{field_name} changed from {current_value!r} to "
                            f"{proposed_value!r} for environment {environment_id} "
                            "without an explicit update()"
                        ),
                    }
                )
        return violations

    def list_for_project(self, project_id: str) -> list[dict[str, Any]]:
        return [p for p in self._profiles.values() if p["project_id"] == project_id]

    def _validate(self, profile: dict[str, Any]) -> None:
        try:
            schemas.validate(profile, "environment_profile")
        except Exception as exc:  # noqa: BLE001
            raise EnvironmentConsistencyEngineError(
                f"Assembled EnvironmentProfile failed validation: {exc}"
            ) from exc
