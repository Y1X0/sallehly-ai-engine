from __future__ import annotations

import uuid
from typing import Any


class SceneGenerator:
    """Expands a StoryOutline's scene_skeleton into full Scene entries
    (packages/schemas/json/scene.schema.json), minus shots - those are
    filled in by the Shot Planner immediately afterward in
    CreativeDirector's orchestration.

    Deterministic by design (see docs/adr/0007): scene structure follows
    directly from the StoryOutline the Story Planner already produced, so
    there is no need for another LLM call here.
    """

    def generate_scenes(self, story_outline: dict[str, Any]) -> list[dict[str, Any]]:
        characters = story_outline.get("continuity_anchors", {}).get("characters", [])
        continuity_notes = story_outline.get("global_style_hint", "")

        scenes = []
        for entry in story_outline["scene_skeleton"]:
            scenes.append(
                {
                    "scene_id": f"scene_{uuid.uuid4().hex[:8]}",
                    "order": entry["order"],
                    "summary": entry["summary"],
                    "location": entry.get("location", ""),
                    "characters": characters,
                    "continuity_notes": continuity_notes,
                    "shots": [],
                }
            )
        return scenes
