from __future__ import annotations

from typing import Any, Literal

ShotPosition = Literal["only", "first", "middle", "last"]

_MIDDLE_SHOT_TYPES = ["medium", "medium_close_up"]
_MIDDLE_MOVEMENTS = ["static", "truck", "handheld"]


class CameraDirector:
    """Deterministic camera planning: for every shot, decides shot type,
    angle, lens (focal length equivalent), movement, and depth of field.

    Rules follow a standard cinematography convention rather than
    inventing one: a multi-shot scene opens on a wide establishing shot,
    closes on a tight detail shot, and rotates through medium framings in
    between. This needs no LLM call - the "creativity" already happened
    in the Story Planner/Scene Generator; this stage is a mechanical
    translation of scene structure into camera parameters.
    """

    def plan_camera(self, shot: dict[str, Any], position: ShotPosition) -> dict[str, Any]:
        if position == "only":
            return self._camera(
                shot_type="medium", angle="eye_level",
                movement_type="static", speed="slow",
                focal_length=35, depth_of_field="medium",
            )
        if position == "first":
            return self._camera(
                shot_type="wide", angle="eye_level",
                movement_type="pan", speed="slow",
                focal_length=24, depth_of_field="deep",
            )
        if position == "last":
            return self._camera(
                shot_type="close_up", angle="eye_level",
                movement_type="dolly_in", speed="slow",
                focal_length=85, depth_of_field="shallow",
            )

        # "middle": rotate through variations keyed by the shot's order,
        # so consecutive middle shots in a scene don't repeat identically.
        index = shot["order"]
        shot_type = _MIDDLE_SHOT_TYPES[index % len(_MIDDLE_SHOT_TYPES)]
        movement_type = _MIDDLE_MOVEMENTS[index % len(_MIDDLE_MOVEMENTS)]
        focal_length = 35 if shot_type == "medium" else 50
        return self._camera(
            shot_type=shot_type, angle="eye_level",
            movement_type=movement_type, speed="medium",
            focal_length=focal_length, depth_of_field="medium",
        )

    @staticmethod
    def _camera(
        *,
        shot_type: str,
        angle: str,
        movement_type: str,
        speed: str,
        focal_length: int,
        depth_of_field: str,
    ) -> dict[str, Any]:
        return {
            "shot_type": shot_type,
            "focal_length_mm_equiv": focal_length,
            "angle": angle,
            "movement": {
                "type": movement_type,
                "speed": speed,
                "easing": "ease_in_out",
            },
            "depth_of_field": depth_of_field,
        }

    @staticmethod
    def position_for(index: int, total: int) -> ShotPosition:
        """Convenience for callers iterating a scene's shots in order."""
        if total == 1:
            return "only"
        if index == 0:
            return "first"
        if index == total - 1:
            return "last"
        return "middle"
