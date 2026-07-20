from __future__ import annotations

from typing import Any

# Deterministic default motion_strength (0-100, normalized - see
# motion.schema.json) per shot type. Wide/establishing shots stay subtle
# (mostly environmental motion); close-ups stay restrained too, since
# strong subject motion at tight framing tends to distort in
# diffusion-based video models; medium shots carry the most motion.
_MOTION_STRENGTH_BY_SHOT_TYPE: dict[str, float] = {
    "extreme_wide": 20.0,
    "wide": 25.0,
    "medium": 45.0,
    "medium_close_up": 40.0,
    "close_up": 35.0,
    "extreme_close_up": 25.0,
    "insert": 30.0,
    "pov": 40.0,
}
_DEFAULT_MOTION_STRENGTH = 35.0

_SUBJECT_MOTION_BY_SHOT_TYPE: dict[str, str] = {
    "extreme_wide": "subtle ambient environmental movement",
    "wide": "natural ambient movement within the wider scene",
    "medium": "natural subject movement within frame",
    "medium_close_up": "restrained, natural subject movement",
    "close_up": "minimal subject movement, subtle expression/detail motion",
    "extreme_close_up": "near-static, only fine natural detail motion",
    "insert": "focused, deliberate motion on the framed detail",
    "pov": "movement matching the point-of-view perspective",
}


class MotionDirector:
    """Deterministic subject-motion planning: motion_strength and a short
    subject_motion description, keyed off the shot type Camera Director
    already chose. Owns subject motion and its timing only - camera
    motion itself belongs to camera.schema.json (Camera Director).
    """

    def plan_motion(self, shot: dict[str, Any], camera: dict[str, Any]) -> dict[str, Any]:
        shot_type = camera["shot_type"]
        return {
            "subject_motion": _SUBJECT_MOTION_BY_SHOT_TYPE.get(
                shot_type, "natural subject movement within frame"
            ),
            "motion_strength": _MOTION_STRENGTH_BY_SHOT_TYPE.get(
                shot_type, _DEFAULT_MOTION_STRENGTH
            ),
            "easing_curve": camera["movement"]["easing"],
            "loopable": False,
        }
