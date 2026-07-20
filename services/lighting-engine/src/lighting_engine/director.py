from __future__ import annotations

from typing import Any

_RIM_LIGHT_SHOT_TYPES = {"close_up", "medium_close_up", "extreme_close_up"}
_ATMOSPHERIC_TIMES_OF_DAY = {"golden_hour", "dusk", "night", "dawn"}

_MOOD_BY_TIME_OF_DAY: dict[str, str] = {
    "dawn": "soft and hopeful",
    "morning": "fresh and clear",
    "midday": "clean and neutral",
    "golden_hour": "warm and intimate",
    "dusk": "cool and contemplative",
    "night": "moody and dramatic",
    "interior_artificial": "controlled and precise",
}
_COLOR_TEMP_BY_TIME_OF_DAY: dict[str, int] = {
    "dawn": 3200,
    "morning": 5000,
    "midday": 5600,
    "golden_hour": 3200,
    "dusk": 4000,
    "night": 4000,
    "interior_artificial": 4300,
}
_GRADING_DIRECTION_BY_TIME_OF_DAY: dict[str, str] = {
    "dawn": "soft highlights, pale cool shadows",
    "morning": "bright, natural, slightly cool",
    "midday": "neutral, balanced tones",
    "golden_hour": "warm highlights, soft shadows",
    "dusk": "cool blues with warm rim accents",
    "night": "cool shadows, warm practicals",
    "interior_artificial": "neutral with controlled contrast",
}


class LightingDirector:
    """Deterministic lighting planning: infers a time_of_day/mood from the
    DirectorPlan's global style, then derives key/fill/rim light, optional
    volumetric atmosphere, and an advisory color-grading direction from
    that. The Style Director owns the final color_grade values on the
    global style - grading_direction here is input to that decision, not
    a competing source of truth (see lighting.schema.json).
    """

    def plan_lighting(self, shot: dict[str, Any], camera: dict[str, Any], global_style: dict[str, Any]) -> dict[str, Any]:
        time_of_day = self._infer_time_of_day(global_style.get("visual_style", ""))
        shot_type = camera["shot_type"]

        return {
            "time_of_day": time_of_day,
            "mood": _MOOD_BY_TIME_OF_DAY[time_of_day],
            "key_light": {
                "direction": "side",
                "hardness": "soft",
                "color_temp_kelvin": _COLOR_TEMP_BY_TIME_OF_DAY[time_of_day],
            },
            "fill_light_ratio": 0.3 if time_of_day == "night" else 0.5,
            "rim_light": shot_type in _RIM_LIGHT_SHOT_TYPES,
            "volumetric_effects": {
                "enabled": time_of_day in _ATMOSPHERIC_TIMES_OF_DAY,
                "intensity": "subtle",
            },
            "grading_direction": _GRADING_DIRECTION_BY_TIME_OF_DAY[time_of_day],
        }

    @staticmethod
    def _infer_time_of_day(visual_style: str) -> str:
        style = visual_style.lower()
        if any(keyword in style for keyword in ("warm", "golden", "premium", "sunset")):
            return "golden_hour"
        if any(keyword in style for keyword in ("night", "dark", "noir")):
            return "night"
        if any(keyword in style for keyword in ("cool", "blue", "cold", "moody")):
            return "dusk"
        if any(keyword in style for keyword in ("interior", "studio", "commercial")):
            return "interior_artificial"
        return "midday"
