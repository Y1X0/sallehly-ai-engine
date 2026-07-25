from __future__ import annotations

from typing import Any

import schemas

from ._util import new_id, now_iso

_OPPOSITE_MOVEMENT = {
    "dolly_in": "dolly_out",
    "dolly_out": "dolly_in",
    "zoom_in": "zoom_out",
    "zoom_out": "zoom_in",
}

# Coarse "how high/low is the camera" ranking used to catch a jump like
# birds_eye straight to low_angle in one cut. Values in the same rank
# (e.g. eye_level/over_the_shoulder/dutch_tilt) are all "normal human
# eye height" variants and never considered a jump against each other.
_ANGLE_HEIGHT_RANK = {
    "low_angle": 1,
    "eye_level": 2,
    "over_the_shoulder": 2,
    "dutch_tilt": 2,
    "high_angle": 3,
    "birds_eye": 4,
}

# Coarse framing-tightness ranking, used together with an angle change to
# catch a combined "impossible" jump (e.g. extreme_wide/birds_eye cutting
# straight to extreme_close_up/low_angle with nothing in between).
_SHOT_TYPE_RANK = {
    "extreme_wide": 0,
    "wide": 1,
    "medium": 2,
    "pov": 2,
    "medium_close_up": 3,
    "close_up": 4,
    "extreme_close_up": 5,
    "insert": 5,
}

_DEFAULT_FOCAL_LENGTH_WARN_MM = 80.0
_DEFAULT_FOCAL_LENGTH_CRITICAL_MM = 200.0
_DEFAULT_RHYTHM_BREAK_RATIO = 2.0


class CameraContinuityEngineError(Exception):
    """Raised when an assembled ContinuityReport fails schema validation."""


class CameraContinuityEngine:
    """Compares two adjacent shots' CameraSetups (camera.schema.json) and
    reports lens/height/movement/rhythm discontinuities that would read
    as an impossible or jarring camera jump rather than a deliberate
    cinematic cut. Produces a ContinuityReport
    (continuity_report.schema.json, scope='camera') keyed by
    '<shot_a_id>-><shot_b_id>' - see
    docs/adr/0013-cinematic-intelligence-layer.md."""

    def check(
        self,
        project_id: str,
        shot_a: dict[str, Any],
        shot_b: dict[str, Any],
        *,
        scene_avg_duration_sec: float | None = None,
        rhythm_break_ratio: float = _DEFAULT_RHYTHM_BREAK_RATIO,
    ) -> dict[str, Any]:
        """`shot_a`/`shot_b` are dicts of shape {"shot_id": str, "camera":
        <camera.schema.json dict>, "duration_sec": float | None}."""
        camera_a, camera_b = shot_a.get("camera") or {}, shot_b.get("camera") or {}
        violations: list[dict[str, Any]] = []
        violations.extend(self._check_focal_length(camera_a, camera_b, shot_a, shot_b))
        violations.extend(self._check_height(camera_a, camera_b, shot_a, shot_b))
        violations.extend(self._check_movement_direction(camera_a, camera_b, shot_a, shot_b))
        violations.extend(self._check_impossible_jump(camera_a, camera_b, shot_a, shot_b))
        if scene_avg_duration_sec is not None:
            violations.extend(self._check_rhythm(shot_b, scene_avg_duration_sec, rhythm_break_ratio))

        report: dict[str, Any] = {
            "schema_version": "1.0",
            "report_id": new_id("cont"),
            "project_id": project_id,
            "scope": "camera",
            "subject_id": f"{shot_a.get('shot_id')}->{shot_b.get('shot_id')}",
            "passed": not any(v["severity"] == "critical" for v in violations),
            "violations": violations,
            "generated_at": now_iso(),
        }
        try:
            schemas.validate(report, "continuity_report")
        except Exception as exc:  # noqa: BLE001
            raise CameraContinuityEngineError(f"Assembled ContinuityReport failed validation: {exc}") from exc
        return report

    def _check_focal_length(
        self, camera_a: dict[str, Any], camera_b: dict[str, Any], shot_a: dict[str, Any], shot_b: dict[str, Any]
    ) -> list[dict[str, Any]]:
        focal_a, focal_b = camera_a.get("focal_length_mm_equiv"), camera_b.get("focal_length_mm_equiv")
        if focal_a is None or focal_b is None:
            return []
        delta = abs(focal_b - focal_a)
        if delta >= _DEFAULT_FOCAL_LENGTH_CRITICAL_MM:
            severity = "critical"
        elif delta >= _DEFAULT_FOCAL_LENGTH_WARN_MM:
            severity = "warning"
        else:
            return []
        return [
            self._violation(
                "focal_length_jump",
                severity,
                f"Focal length jumped {delta:.0f}mm ({focal_a}mm -> {focal_b}mm) between "
                f"{shot_a.get('shot_id')} and {shot_b.get('shot_id')}",
                shot_a,
                shot_b,
            )
        ]

    def _check_height(
        self, camera_a: dict[str, Any], camera_b: dict[str, Any], shot_a: dict[str, Any], shot_b: dict[str, Any]
    ) -> list[dict[str, Any]]:
        angle_a, angle_b = camera_a.get("angle"), camera_b.get("angle")
        rank_a, rank_b = _ANGLE_HEIGHT_RANK.get(angle_a), _ANGLE_HEIGHT_RANK.get(angle_b)
        if rank_a is None or rank_b is None or abs(rank_b - rank_a) < 2:
            return []
        return [
            self._violation(
                "camera_height_jump",
                "critical",
                f"Camera height jumped from {angle_a!r} to {angle_b!r} between "
                f"{shot_a.get('shot_id')} and {shot_b.get('shot_id')}",
                shot_a,
                shot_b,
            )
        ]

    def _check_movement_direction(
        self, camera_a: dict[str, Any], camera_b: dict[str, Any], shot_a: dict[str, Any], shot_b: dict[str, Any]
    ) -> list[dict[str, Any]]:
        type_a = (camera_a.get("movement") or {}).get("type")
        type_b = (camera_b.get("movement") or {}).get("type")
        if type_a is None or type_b is None or _OPPOSITE_MOVEMENT.get(type_a) != type_b:
            return []
        return [
            self._violation(
                "camera_direction_flip",
                "warning",
                f"Camera movement flipped from {type_a!r} to {type_b!r} between "
                f"{shot_a.get('shot_id')} and {shot_b.get('shot_id')}",
                shot_a,
                shot_b,
            )
        ]

    def _check_impossible_jump(
        self, camera_a: dict[str, Any], camera_b: dict[str, Any], shot_a: dict[str, Any], shot_b: dict[str, Any]
    ) -> list[dict[str, Any]]:
        shot_type_a, shot_type_b = camera_a.get("shot_type"), camera_b.get("shot_type")
        rank_a, rank_b = _SHOT_TYPE_RANK.get(shot_type_a), _SHOT_TYPE_RANK.get(shot_type_b)
        angle_changed = camera_a.get("angle") != camera_b.get("angle") and camera_a.get("angle") and camera_b.get("angle")
        if rank_a is None or rank_b is None or abs(rank_b - rank_a) < 4 or not angle_changed:
            return []
        return [
            self._violation(
                "impossible_camera_jump",
                "critical",
                f"Framing jumped from {shot_type_a!r}/{camera_a.get('angle')!r} straight to "
                f"{shot_type_b!r}/{camera_b.get('angle')!r} between "
                f"{shot_a.get('shot_id')} and {shot_b.get('shot_id')} with no intermediate shot",
                shot_a,
                shot_b,
            )
        ]

    def _check_rhythm(
        self, shot_b: dict[str, Any], scene_avg_duration_sec: float, ratio: float
    ) -> list[dict[str, Any]]:
        duration = shot_b.get("duration_sec")
        if duration is None or scene_avg_duration_sec <= 0:
            return []
        if duration >= scene_avg_duration_sec * ratio or duration <= scene_avg_duration_sec / ratio:
            return [
                {
                    "violation_type": "shot_rhythm_break",
                    "severity": "info",
                    "description": (
                        f"{shot_b.get('shot_id')} runs {duration:.1f}s against a scene "
                        f"average of {scene_avg_duration_sec:.1f}s"
                    ),
                    "shot_id": shot_b.get("shot_id"),
                }
            ]
        return []

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
