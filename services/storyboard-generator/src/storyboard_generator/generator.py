from __future__ import annotations

from typing import Any

import schemas

_MOVEMENT_DISPLAY = {
    "dolly_in": "dolly-in",
    "dolly_out": "dolly-out",
    "zoom_in": "zoom-in",
    "zoom_out": "zoom-out",
}


class StoryboardGenerator:
    """Renders every shot's already-populated camera/motion/lighting into
    a human-readable Storyboard frame for approval (gate 1). Purely a
    presentation layer over data the Camera/Motion/Lighting/Style
    Directors already decided - no new creative decisions are made here,
    so this is deterministic and needs no LLM call.
    """

    def generate(self, director_plan: dict[str, Any]) -> dict[str, Any]:
        frames = []
        for scene in director_plan["scenes"]:
            for shot in scene["shots"]:
                frames.append(self._frame(scene, shot))

        return {
            "project_id": director_plan["project_id"],
            "director_plan_version": schemas.content_hash(director_plan),
            "status": "pending_review",
            "frames": frames,
        }

    def _frame(self, scene: dict[str, Any], shot: dict[str, Any]) -> dict[str, Any]:
        camera = shot["camera"]
        lighting = shot["lighting"]

        return {
            "frame_id": f"frame_{shot['shot_id']}",
            "shot_id": shot["shot_id"],
            "visual_description": shot["description"],
            "camera_framing": self._camera_framing(camera),
            "lens_choice": self._lens_choice(camera),
            "camera_movement": self._camera_movement(camera),
            "lighting": self._lighting_summary(lighting),
            "environment": scene.get("location") or "unspecified setting",
            "mood": lighting["mood"],
            "transition": self._transition(shot),
        }

    @staticmethod
    def _display(value: str) -> str:
        return _MOVEMENT_DISPLAY.get(value, value.replace("_", " "))

    def _camera_framing(self, camera: dict[str, Any]) -> str:
        return f"{self._display(camera['shot_type'])} shot, {self._display(camera['angle'])}"

    @staticmethod
    def _lens_choice(camera: dict[str, Any]) -> str:
        return (
            f"{camera['focal_length_mm_equiv']}mm equivalent, "
            f"{camera['depth_of_field']} depth of field"
        )

    def _camera_movement(self, camera: dict[str, Any]) -> str:
        movement = camera["movement"]
        return (
            f"{self._display(movement['type'])}, {movement['speed']} speed, "
            f"{self._display(movement['easing'])} easing"
        )

    def _lighting_summary(self, lighting: dict[str, Any]) -> str:
        key_light = lighting.get("key_light", {})
        parts = [
            f"{self._display(lighting['time_of_day'])} lighting",
            f"key light {key_light.get('direction', 'side')} ({key_light.get('hardness', 'soft')})",
            lighting["grading_direction"],
        ]
        if lighting.get("volumetric_effects", {}).get("enabled"):
            parts.append("subtle atmospheric haze")
        return ", ".join(parts)

    def _transition(self, shot: dict[str, Any]) -> str:
        transition_in = self._display(shot.get("transition_in", "cut"))
        transition_out = self._display(shot.get("transition_out", "cut"))
        return f"{transition_in} in, {transition_out} out"
