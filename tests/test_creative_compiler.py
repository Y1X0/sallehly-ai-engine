"""Tests for the Phase 2 Creative Compiler:

    DirectorPlan (bare shots)
      -> Style/Camera/Motion/Lighting Directors -> Storyboard (gate 1)
      -> Render Specification Generator -> RenderPlan (gate 2)

Unit tests build a bare DirectorPlan by hand (no LLM involved - Phase 2
is entirely deterministic). The final test exercises the true end-to-end
path from a raw idea through both approval gates, using CreativeDirector
+ FakeLLMProvider for the Phase 1 half.
"""

from __future__ import annotations

import pytest
import schemas
from creative_compiler import CreativeCompiler
from director_memory import InMemoryDirectorMemoryStore
from video_engine_sdk import CapabilityManifest

TEST_MANIFEST = CapabilityManifest(
    engine_id="test-engine",
    engine_version="0.1.0",
    modes=["text_to_video", "image_to_video"],
    max_shot_duration_sec=5.0,
    min_shot_duration_sec=1.0,
    resolutions=["832x480", "1280x720"],
    fps_options=[24, 16],
    motion_strength_range=(0.0, 10.0),
    supports_negative_prompt=True,
    supports_seed=True,
    supports_conditioning_images=True,
    max_conditioning_images=1,
)

TIGHT_MANIFEST = CapabilityManifest(
    engine_id="tight-test-engine",
    engine_version="0.1.0",
    modes=["text_to_video"],
    max_shot_duration_sec=2.0,
    min_shot_duration_sec=1.0,
    resolutions=["832x480"],
    fps_options=[24],
)


def _shot(shot_id: str, order: int, duration_sec: float, description: str) -> dict:
    return {
        "shot_id": shot_id,
        "order": order,
        "duration_sec": duration_sec,
        "description": description,
        "transition_in": "fade_from_black" if order == 0 else "cut",
        "transition_out": "cut",
    }


def build_bare_director_plan(project_id: str = "proj_p2") -> dict:
    return {
        "schema_version": "1.0",
        "project_id": project_id,
        "logline": "A minimalist watch is revealed through warm, premium close-ups.",
        "target_duration_sec": 20,
        "aspect_ratio": "16:9",
        "global_style": {"visual_style": "product commercial clean, warm premium lighting"},
        "negative_prompt_global": "distorted anatomy, watermark, low quality",
        "continuity_notes": "studio",
        "scenes": [
            {
                "scene_id": "scene_0",
                "order": 0,
                "summary": "Macro reveal of the watch face catching warm light.",
                "location": "studio",
                "characters": [],
                "continuity_notes": "studio",
                "shots": [
                    _shot("shot_0_0", 0, 3.0, "Macro reveal of the watch face, shot 1 of 2"),
                    _shot("shot_0_1", 1, 3.0, "Macro reveal of the watch face, shot 2 of 2"),
                ],
            },
            {
                "scene_id": "scene_1",
                "order": 1,
                "summary": "Close-ups of strap texture and dial craftsmanship.",
                "location": "studio",
                "characters": [],
                "continuity_notes": "studio",
                "shots": [
                    _shot("shot_1_0", 0, 6.0, "Strap texture close-up, shot 1 of 1"),
                ],
            },
            {
                "scene_id": "scene_2",
                "order": 2,
                "summary": "Full product shot with logo.",
                "location": "studio",
                "characters": [],
                "continuity_notes": "studio",
                "shots": [
                    _shot("shot_2_0", 0, 3.0, "Full product shot with logo, shot 1 of 2"),
                    _shot("shot_2_1", 1, 3.0, "Full product shot with logo, shot 2 of 2"),
                ],
            },
        ],
    }


def test_compile_storyboard_populates_every_shot_and_is_schema_valid():
    compiler = CreativeCompiler(capability_manifest=TEST_MANIFEST)
    director_plan = build_bare_director_plan()

    enriched_plan, storyboard = compiler.compile_storyboard(director_plan)

    schemas.validate(enriched_plan, "director_plan")
    schemas.validate(storyboard, "storyboard")
    assert storyboard["status"] == "pending_review"

    total_shots = sum(len(scene["shots"]) for scene in enriched_plan["scenes"])
    assert len(storyboard["frames"]) == total_shots

    for scene in enriched_plan["scenes"]:
        for shot in scene["shots"]:
            assert shot["camera"]["shot_type"]
            assert shot["motion"]["motion_strength"] >= 0
            assert shot["lighting"]["time_of_day"]

    for frame in storyboard["frames"]:
        assert frame["camera_framing"]
        assert frame["lens_choice"]
        assert frame["camera_movement"]
        assert frame["lighting"]
        assert frame["environment"] == "studio"
        assert frame["mood"]
        assert frame["transition"]


def test_first_and_last_shot_in_multi_shot_scene_differ():
    compiler = CreativeCompiler(capability_manifest=TEST_MANIFEST)
    enriched_plan, _ = compiler.compile_storyboard(build_bare_director_plan())

    scene_0_shots = enriched_plan["scenes"][0]["shots"]
    assert scene_0_shots[0]["camera"]["shot_type"] == "wide"
    assert scene_0_shots[-1]["camera"]["shot_type"] == "close_up"

    single_shot_scene = enriched_plan["scenes"][1]["shots"]
    assert single_shot_scene[0]["camera"]["shot_type"] == "medium"


def test_approve_and_reject_storyboard():
    compiler = CreativeCompiler(capability_manifest=TEST_MANIFEST)
    director_plan = build_bare_director_plan()
    _, storyboard = compiler.compile_storyboard(director_plan)

    approved = compiler.approve_storyboard(director_plan["project_id"], storyboard)
    assert approved["status"] == "approved"

    rejected = compiler.request_storyboard_changes(
        director_plan["project_id"], storyboard, feedback=[{"frame_id": "frame_shot_0_0", "comment": "too static"}]
    )
    assert rejected["status"] == "changes_requested"
    assert rejected["reviewer_feedback"][0]["comment"] == "too static"


def test_compile_render_plan_requires_approved_storyboard():
    compiler = CreativeCompiler(capability_manifest=TEST_MANIFEST)
    director_plan = build_bare_director_plan()
    compiler.compile_storyboard(director_plan)  # leaves status = pending_review

    with pytest.raises(ValueError, match="approved"):
        compiler.compile_render_plan(director_plan["project_id"])


def test_compile_render_plan_produces_valid_render_specs():
    compiler = CreativeCompiler(capability_manifest=TEST_MANIFEST)
    director_plan = build_bare_director_plan()
    _, storyboard = compiler.compile_storyboard(director_plan)
    compiler.approve_storyboard(director_plan["project_id"], storyboard)

    render_plan = compiler.compile_render_plan(director_plan["project_id"])

    schemas.validate(render_plan, "render_plan")
    assert render_plan["status"] == "pending_review"
    assert render_plan["engine_id"] == "test-engine"

    # scene_1's single 6s shot exceeds TEST_MANIFEST.max_shot_duration_sec (5s),
    # so it splits into 2 parts; the four 3s shots don't split. 4 + 2 = 6.
    assert len(render_plan["render_specs"]) == 6
    assert {spec["shot_id"] for spec in render_plan["render_specs"]} == {
        "shot_0_0", "shot_0_1", "shot_1_0_part1", "shot_1_0_part2", "shot_2_0", "shot_2_1",
    }

    for spec in render_plan["render_specs"]:
        assert 0.0 <= spec["motion_strength"] <= 10.0  # TEST_MANIFEST.motion_strength_range
        assert spec["resolution"] in TEST_MANIFEST.resolutions
        assert spec["fps"] in TEST_MANIFEST.fps_options
        assert spec["engine_id"] == "test-engine"

    approved = compiler.approve_render_plan(director_plan["project_id"], render_plan)
    assert approved["status"] == "approved"


def test_duration_splitting_against_a_tight_capability_manifest():
    compiler = CreativeCompiler(capability_manifest=TIGHT_MANIFEST)
    director_plan = build_bare_director_plan()
    _, storyboard = compiler.compile_storyboard(director_plan)
    compiler.approve_storyboard(director_plan["project_id"], storyboard)

    render_plan = compiler.compile_render_plan(director_plan["project_id"])
    schemas.validate(render_plan, "render_plan")

    # scene_1's single 6s shot must split into ceil(6/2)=3 parts under a 2s cap.
    split_specs = [spec for spec in render_plan["render_specs"] if spec["shot_id"].startswith("shot_1_0_part")]
    assert len(split_specs) == 3
    for spec in split_specs:
        assert spec["duration_sec"] <= 2.0
    assert sum(spec["duration_sec"] for spec in split_specs) == pytest.approx(6.0, abs=0.05)

    # scene_0/scene_2's 3s shots fit under the 2s cap? No - 3s > 2s cap, so they split too.
    split_ids = {spec["shot_id"].rsplit("_part", 1)[0] for spec in render_plan["render_specs"] if "_part" in spec["shot_id"]}
    assert "shot_0_0" in split_ids


def test_full_pipeline_brief_to_approved_render_plan():
    """True end-to-end: raw idea -> CreativeDirector (FakeLLMProvider) ->
    CreativeCompiler -> both approval gates -> RenderPlan."""
    from ai_director import CreativeDirector, ProjectBrief
    from llm_providers.testing import FakeLLMProvider

    fake_creative_brief = {
        "genre": "product commercial",
        "tone_keywords": ["warm", "premium", "minimalist"],
        "target_audience": "young professionals",
        "key_message": "Timeless elegance for the modern professional.",
        "must_include": [],
        "must_avoid": [],
        "inferred_target_duration_sec": None,
        "inferred_aspect_ratio": None,
        "ambiguities": [],
    }
    fake_story_outline = {
        "logline": "A minimalist watch is revealed through warm, premium close-ups.",
        "narrative_arc": [
            {"beat_id": "beat_1", "order": 0, "purpose": "hook", "description": "Macro reveal."},
        ],
        "scene_skeleton": [
            {"order": 0, "role": "hero_shot", "summary": "Macro reveal of the watch.", "location": "studio", "estimated_duration_sec": 6.0},
            {"order": 1, "role": "closing_brand_beat", "summary": "Full product shot with logo.", "location": "studio", "estimated_duration_sec": 6.0},
        ],
        "continuity_anchors": {"characters": [], "locations": ["studio"]},
        "global_style_hint": "product commercial clean, warm premium lighting",
    }

    memory = InMemoryDirectorMemoryStore()
    fake_llm = FakeLLMProvider([fake_creative_brief, fake_story_outline])
    director = CreativeDirector(llm_provider=fake_llm, memory=memory)
    brief = ProjectBrief(
        project_id="proj_e2e_p2",
        prompt="A 12-second product ad for a minimalist watch brand, warm and premium mood",
        target_duration_sec=12,
        aspect_ratio="16:9",
    )
    director_plan = director.generate_director_plan(brief)

    compiler = CreativeCompiler(capability_manifest=TEST_MANIFEST, memory=memory)
    _, storyboard = compiler.compile_storyboard(director_plan)
    compiler.approve_storyboard(brief.project_id, storyboard)

    render_plan = compiler.compile_render_plan(brief.project_id)
    approved_render_plan = compiler.approve_render_plan(brief.project_id, render_plan)

    schemas.validate(approved_render_plan, "render_plan")
    assert approved_render_plan["status"] == "approved"
    assert len(approved_render_plan["render_specs"]) >= 1
