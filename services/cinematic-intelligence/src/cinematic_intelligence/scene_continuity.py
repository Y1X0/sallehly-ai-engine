from __future__ import annotations

from typing import TYPE_CHECKING, Any

import schemas

from ._util import new_id, now_iso

if TYPE_CHECKING:
    from .character_consistency import CharacterConsistencyEngine
    from .environment_consistency import EnvironmentConsistencyEngine
    from .object_consistency import ObjectConsistencyEngine

# The classic 180-degree-rule pairing: a subject exiting screen-right
# should enter the next shot from screen-left, and vice versa. Any other
# pair of distinct values (e.g. "door" -> "window") is treated as a real
# mismatch; identical values (leaving and entering through the same named
# point) are always compatible.
_COMPATIBLE_EXIT_ENTRY = {
    "screen_left": "screen_right",
    "screen_right": "screen_left",
}

_OPPOSITE_MOTION = {
    "left_to_right": "right_to_left",
    "right_to_left": "left_to_right",
    "toward_camera": "away_from_camera",
    "away_from_camera": "toward_camera",
}


class SceneContinuityEngineError(Exception):
    """Raised when an assembled ContinuityReport fails schema validation."""


class SceneContinuityEngine:
    """Compares two adjacent shots within the same scene and reports
    every continuity rule they might violate: entry/exit point matching,
    eye lines, actor positions, motion direction, scene timing, and
    (via the Environment/Object/Character Consistency Engines, when
    supplied) environment jumps, object location conflicts, and
    references to characters that were never established. Produces a
    ContinuityReport (continuity_report.schema.json, scope='scene') -
    see docs/adr/0013-cinematic-intelligence-layer.md.

    Each shot argument is a plain dict (this engine has no schema of its
    own for "a shot's continuity state" - it reads whichever of these
    optional keys the caller has available):

        shot_id, entry_point, exit_point, eye_line, motion_direction,
        actor_positions ({character_id: position_str}),
        object_locations ({object_id: location_str}),
        character_ids (list[str]), environment_id, timing_sec,
        duration_sec
    """

    def check(
        self,
        project_id: str,
        scene_id: str,
        shot_a: dict[str, Any],
        shot_b: dict[str, Any],
        *,
        environment_engine: "EnvironmentConsistencyEngine | None" = None,
        object_engine: "ObjectConsistencyEngine | None" = None,
        character_engine: "CharacterConsistencyEngine | None" = None,
        max_timing_gap_sec: float = 0.5,
    ) -> dict[str, Any]:
        violations: list[dict[str, Any]] = []
        violations.extend(self._check_entry_exit(shot_a, shot_b))
        violations.extend(self._check_eye_line(shot_a, shot_b))
        violations.extend(self._check_actor_positions(shot_a, shot_b))
        violations.extend(self._check_motion_direction(shot_a, shot_b))
        violations.extend(self._check_timing(shot_a, shot_b, max_timing_gap_sec))
        if environment_engine is not None:
            violations.extend(self._check_environment(shot_b, environment_engine))
        if object_engine is not None:
            violations.extend(self._check_objects(shot_b, object_engine))
        if character_engine is not None:
            violations.extend(self._check_characters(shot_b, character_engine))

        report: dict[str, Any] = {
            "schema_version": "1.0",
            "report_id": new_id("cont"),
            "project_id": project_id,
            "scope": "scene",
            "subject_id": scene_id,
            "passed": not any(v["severity"] == "critical" for v in violations),
            "violations": violations,
            "generated_at": now_iso(),
        }
        try:
            schemas.validate(report, "continuity_report")
        except Exception as exc:  # noqa: BLE001
            raise SceneContinuityEngineError(f"Assembled ContinuityReport failed validation: {exc}") from exc
        return report

    def _check_entry_exit(self, shot_a: dict[str, Any], shot_b: dict[str, Any]) -> list[dict[str, Any]]:
        exit_point = shot_a.get("exit_point")
        entry_point = shot_b.get("entry_point")
        if not exit_point or not entry_point:
            return []
        compatible = entry_point == exit_point or _COMPATIBLE_EXIT_ENTRY.get(exit_point) == entry_point
        if compatible:
            return []
        return [
            self._violation(
                "entry_exit_mismatch",
                "warning",
                f"Shot {shot_a.get('shot_id')} exits via {exit_point!r} but "
                f"{shot_b.get('shot_id')} enters via {entry_point!r}",
                shot_a,
                shot_b,
            )
        ]

    def _check_eye_line(self, shot_a: dict[str, Any], shot_b: dict[str, Any]) -> list[dict[str, Any]]:
        eye_a, eye_b = shot_a.get("eye_line"), shot_b.get("eye_line")
        if not eye_a or not eye_b or eye_a == eye_b:
            return []
        if shot_b.get("motion_direction", "static") in (None, "static"):
            return [
                self._violation(
                    "eye_line_mismatch",
                    "warning",
                    f"Eye line shifted from {eye_a!r} to {eye_b!r} between "
                    f"{shot_a.get('shot_id')} and {shot_b.get('shot_id')} with no recorded motion",
                    shot_a,
                    shot_b,
                )
            ]
        return []

    def _check_actor_positions(self, shot_a: dict[str, Any], shot_b: dict[str, Any]) -> list[dict[str, Any]]:
        positions_a = shot_a.get("actor_positions") or {}
        positions_b = shot_b.get("actor_positions") or {}
        static = shot_b.get("motion_direction", "static") in (None, "static")
        violations = []
        for character_id, position_b in positions_b.items():
            position_a = positions_a.get(character_id)
            if position_a is not None and position_a != position_b and static:
                violations.append(
                    self._violation(
                        "actor_position_jump",
                        "warning",
                        f"{character_id} moved from {position_a!r} to {position_b!r} "
                        f"between {shot_a.get('shot_id')} and {shot_b.get('shot_id')} with no recorded motion",
                        shot_a,
                        shot_b,
                    )
                )
        return violations

    def _check_motion_direction(self, shot_a: dict[str, Any], shot_b: dict[str, Any]) -> list[dict[str, Any]]:
        motion_a, motion_b = shot_a.get("motion_direction"), shot_b.get("motion_direction")
        if not motion_a or not motion_b:
            return []
        if _OPPOSITE_MOTION.get(motion_a) == motion_b:
            return [
                self._violation(
                    "motion_direction_flip",
                    "warning",
                    f"Motion direction flipped from {motion_a!r} to {motion_b!r} "
                    f"between {shot_a.get('shot_id')} and {shot_b.get('shot_id')}",
                    shot_a,
                    shot_b,
                )
            ]
        return []

    def _check_timing(
        self, shot_a: dict[str, Any], shot_b: dict[str, Any], max_gap: float
    ) -> list[dict[str, Any]]:
        timing_a, duration_a, timing_b = shot_a.get("timing_sec"), shot_a.get("duration_sec"), shot_b.get("timing_sec")
        if timing_a is None or duration_a is None or timing_b is None:
            return []
        gap = timing_b - (timing_a + duration_a)
        if gap > max_gap or gap < -1e-6:
            return [
                self._violation(
                    "timing_gap",
                    "info",
                    f"{'Gap' if gap > 0 else 'Overlap'} of {abs(gap):.2f}s between "
                    f"{shot_a.get('shot_id')} and {shot_b.get('shot_id')}",
                    shot_a,
                    shot_b,
                )
            ]
        return []

    def _check_environment(
        self, shot_b: dict[str, Any], environment_engine: "EnvironmentConsistencyEngine"
    ) -> list[dict[str, Any]]:
        environment_id = shot_b.get("environment_id")
        if not environment_id or not environment_engine.exists(environment_id):
            return []
        proposed = {k: shot_b[k] for k in ("weather", "time_of_day", "season", "sky") if k in shot_b}
        drift = environment_engine.detect_drift(environment_id, proposed)
        for violation in drift:
            violation.setdefault("shot_id", shot_b.get("shot_id"))
        return drift

    def _check_objects(self, shot_b: dict[str, Any], object_engine: "ObjectConsistencyEngine") -> list[dict[str, Any]]:
        object_locations = shot_b.get("object_locations") or {}
        violations = []
        for object_id, claimed_location in object_locations.items():
            if not object_engine.exists(object_id):
                continue
            established_location = object_engine.current_location(object_id)
            if established_location is not None and established_location != claimed_location:
                violations.append(
                    self._violation(
                        "object_location_conflict",
                        "warning",
                        f"{object_id} was last established at {established_location!r} but "
                        f"{shot_b.get('shot_id')} claims {claimed_location!r}",
                        shot_b,
                        shot_b,
                    )
                )
        return violations

    def _check_characters(
        self, shot_b: dict[str, Any], character_engine: "CharacterConsistencyEngine"
    ) -> list[dict[str, Any]]:
        violations = []
        for character_id in shot_b.get("character_ids") or []:
            if not character_engine.exists(character_id):
                violations.append(
                    {
                        "violation_type": "character_identity_drift",
                        "severity": "critical",
                        "description": (
                            f"{shot_b.get('shot_id')} references character {character_id!r} "
                            "which has no established CharacterIdentityProfile - identity "
                            "would have to be regenerated instead of reused"
                        ),
                        "shot_id": shot_b.get("shot_id"),
                    }
                )
        return violations

    def _violation(
        self,
        violation_type: str,
        severity: str,
        description: str,
        shot_a: dict[str, Any],
        shot_b: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "violation_type": violation_type,
            "severity": severity,
            "description": description,
            "shot_id": shot_b.get("shot_id"),
            "related_shot_id": shot_a.get("shot_id"),
        }
