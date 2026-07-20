"""End-to-end test of the Phase 1 Creative Director pipeline:

    ProjectBrief -> CreativeBriefParser -> StoryPlanner
                 -> SceneGenerator -> ShotPlanner -> DirectorPlan

Uses FakeLLMProvider (packages/llm-providers) so it runs with no network
access and no API key, while still exercising every real seam: prompt
template rendering, schema validation, RetryingLLMProvider, and the
CreativeDirector assembly/merge logic.
"""

from __future__ import annotations

import pytest
import schemas
from ai_director import CreativeDirector, ProjectBrief
from director_memory import InMemoryDirectorMemoryStore
from llm_providers.testing import FakeLLMProvider

FAKE_CREATIVE_BRIEF = {
    "genre": "product commercial",
    "tone_keywords": ["warm", "premium", "minimalist"],
    "target_audience": "young professionals",
    "key_message": "This watch is timeless elegance for the modern professional.",
    "must_include": ["the watch"],
    "must_avoid": ["cluttered backgrounds"],
    "inferred_target_duration_sec": None,
    "inferred_aspect_ratio": None,
    "ambiguities": [],
}

FAKE_STORY_OUTLINE = {
    "logline": "A minimalist watch is revealed through warm, premium close-ups that speak to timeless elegance.",
    "narrative_arc": [
        {"beat_id": "beat_1", "order": 0, "purpose": "hook", "description": "Open on an evocative macro shot of the watch face."},
        {"beat_id": "beat_2", "order": 1, "purpose": "build", "description": "Reveal craftsmanship details."},
        {"beat_id": "beat_3", "order": 2, "purpose": "resolution", "description": "Full product shot with brand mark."},
    ],
    "scene_skeleton": [
        {"order": 0, "role": "hero_shot", "summary": "Macro reveal of the watch face catching warm light.", "location": "studio", "estimated_duration_sec": 6.0},
        {"order": 1, "role": "feature_highlights", "summary": "Close-ups of strap texture and dial craftsmanship.", "location": "studio", "estimated_duration_sec": 8.0},
        {"order": 2, "role": "closing_brand_beat", "summary": "Full product shot with logo.", "location": "studio", "estimated_duration_sec": 6.0},
    ],
    "continuity_anchors": {"characters": [], "locations": ["studio"]},
    "global_style_hint": "product commercial clean, warm premium lighting",
}


def build_director() -> CreativeDirector:
    fake_llm = FakeLLMProvider([FAKE_CREATIVE_BRIEF, FAKE_STORY_OUTLINE])
    return CreativeDirector(llm_provider=fake_llm, memory=InMemoryDirectorMemoryStore())


def test_generate_director_plan_is_schema_valid():
    director = build_director()
    brief = ProjectBrief(
        project_id="proj_test_1",
        prompt="A 20-second product ad for a minimalist watch brand, warm and premium mood",
        target_duration_sec=20,
        aspect_ratio="16:9",
    )

    plan = director.generate_director_plan(brief)

    schemas.validate(plan, "director_plan")
    assert plan["project_id"] == "proj_test_1"
    assert plan["logline"] == FAKE_STORY_OUTLINE["logline"]
    assert len(plan["scenes"]) == 3
    for scene in plan["scenes"]:
        assert len(scene["shots"]) >= 1
        for shot in scene["shots"]:
            schemas.validate(shot, "shot")


def test_scene_shot_durations_sum_to_scene_budget():
    director = build_director()
    brief = ProjectBrief(
        project_id="proj_test_2",
        prompt="A 20-second product ad",
        target_duration_sec=20,
        aspect_ratio="16:9",
    )

    plan = director.generate_director_plan(brief)

    for scene, skeleton_entry in zip(plan["scenes"], FAKE_STORY_OUTLINE["scene_skeleton"], strict=True):
        total = sum(shot["duration_sec"] for shot in scene["shots"])
        assert total == pytest.approx(skeleton_entry["estimated_duration_sec"], abs=0.05)


def test_memory_records_every_stage():
    memory = InMemoryDirectorMemoryStore()
    fake_llm = FakeLLMProvider([FAKE_CREATIVE_BRIEF, FAKE_STORY_OUTLINE])
    director = CreativeDirector(llm_provider=fake_llm, memory=memory)
    brief = ProjectBrief(
        project_id="proj_test_3",
        prompt="A 20-second product ad",
        target_duration_sec=20,
        aspect_ratio="16:9",
    )

    director.generate_director_plan(brief)

    assert memory.latest("proj_test_3", "creative_brief") is not None
    assert memory.latest("proj_test_3", "story_outline") is not None
    assert memory.latest("proj_test_3", "director_plan") is not None


def test_regenerate_with_feedback_reinvokes_story_planner():
    revised_story_outline = dict(FAKE_STORY_OUTLINE, logline="A revised, warmer logline.")
    fake_llm = FakeLLMProvider([FAKE_CREATIVE_BRIEF, FAKE_STORY_OUTLINE, revised_story_outline])
    director = CreativeDirector(llm_provider=fake_llm, memory=InMemoryDirectorMemoryStore())
    brief = ProjectBrief(
        project_id="proj_test_4",
        prompt="A 20-second product ad",
        target_duration_sec=20,
        aspect_ratio="16:9",
    )
    director.generate_director_plan(brief)

    revised_plan = director.regenerate_with_feedback(
        "proj_test_4", feedback=["Make the tone warmer"]
    )

    schemas.validate(revised_plan, "director_plan")
    assert revised_plan["logline"] == "A revised, warmer logline."
