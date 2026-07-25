"""CinematicIntelligenceCoordinator (services/cinematic-intelligence):
the Phase 8 integration point wiring every Phase 7 engine into the real
project pipeline - real DirectorPlan/RenderPlan fixtures in, real
continuity violations/prompt enrichment/repair actions out."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from cinematic_intelligence import CinematicIntelligenceCoordinator, CinematicIntelligenceCoordinatorError

sys.path.insert(0, str(Path(__file__).parent))
from test_creative_compiler import TEST_MANIFEST, build_bare_director_plan  # noqa: E402
from creative_compiler import CreativeCompiler  # noqa: E402
from director_memory import InMemoryDirectorMemoryStore  # noqa: E402


def _compiled_plan_and_render_plan(project_id: str = "proj_ci"):
    memory = InMemoryDirectorMemoryStore()
    compiler = CreativeCompiler(capability_manifest=TEST_MANIFEST, memory=memory)
    plan = build_bare_director_plan(project_id)
    enriched, storyboard = compiler.compile_storyboard(plan)
    compiler.approve_storyboard(project_id, storyboard)
    render_plan = compiler.compile_render_plan(project_id)
    return enriched, render_plan


def _shot(shot_id, camera=None, motion=None, lighting=None, duration=2.0, description="a shot"):
    return {
        "shot_id": shot_id,
        "order": 0,
        "duration_sec": duration,
        "description": description,
        "camera": camera or {},
        "motion": motion or {},
        "lighting": lighting or {},
    }


def _two_shot_plan(project_id="proj_smoke"):
    director_plan = {
        "project_id": project_id,
        "global_style": {"visual_style": "cinematic photorealistic"},
        "scenes": [
            {
                "scene_id": "scene_1",
                "location": "Rooftop at dusk",
                "characters": ["Alice"],
                "shots": [
                    _shot(
                        "shot_1",
                        camera={"shot_type": "extreme_wide", "angle": "birds_eye", "focal_length_mm_equiv": 24, "movement": {"type": "static"}},
                        motion={"motion_strength": 20, "subject_motion": "Alice stands still"},
                        lighting={"time_of_day": "dusk", "mood": "warm"},
                        description="Alice looks out over the city",
                    ),
                    {
                        **_shot(
                            "shot_2",
                            camera={"shot_type": "extreme_close_up", "angle": "low_angle", "focal_length_mm_equiv": 300, "movement": {"type": "static"}},
                            motion={"motion_strength": 5, "subject_motion": "Alice remains still"},
                            lighting={"time_of_day": "dusk", "mood": "warm"},
                            description="Close on Alice, her eyes narrow",
                        ),
                        "order": 1,
                    },
                ],
            }
        ],
    }
    render_plan = {
        "project_id": project_id,
        "engine_id": "wan2.1",
        "status": "pending_review",
        "render_specs": [
            {"schema_version": "1.0", "shot_id": "shot_1", "duration_sec": 2.0, "fps": 24, "resolution": "1280x720", "positive_prompt": "placeholder"},
            {"schema_version": "1.0", "shot_id": "shot_2", "duration_sec": 2.0, "fps": 24, "resolution": "1280x720", "positive_prompt": "placeholder"},
        ],
    }
    return director_plan, render_plan


class TestEnrichRenderPlan:
    def test_patches_every_render_spec_prompt(self):
        # Uses the hand-crafted two-shot fixture (real scene location +
        # named character) rather than the compiled bare-manifest fixture:
        # the compiled fixture's "studio, no characters" shots can
        # coincidentally produce a CIL-enriched prompt that is
        # character-for-character identical to RenderConfigCompiler's own
        # originally-compiled prompt for that shot, since both draw from
        # very similar camera/lighting/description fields. The two-shot
        # fixture starts from a literal "placeholder" string, which real
        # generated prose will never coincidentally match.
        coordinator = CinematicIntelligenceCoordinator()
        director_plan, render_plan = _two_shot_plan("proj_patch")
        original_prompts = [spec["positive_prompt"] for spec in render_plan["render_specs"]]

        enriched = coordinator.enrich_render_plan(director_plan, render_plan)

        assert enriched is render_plan
        for spec, original in zip(enriched["render_specs"], original_prompts):
            assert spec["positive_prompt"] != original
            assert "blurry" in spec["negative_prompt"]

    def test_establishes_character_once_and_reuses_across_shots(self):
        coordinator = CinematicIntelligenceCoordinator()
        director_plan, render_plan = _two_shot_plan("proj_reuse")
        coordinator.enrich_render_plan(director_plan, render_plan)

        profiles = coordinator.characters.list_for_project("proj_reuse")
        assert len(profiles) == 1
        assert profiles[0]["display_name"] == "Alice"
        # Both shots' prompts reference the same identity description.
        assert all("Alice" in spec["positive_prompt"] for spec in render_plan["render_specs"])

    def test_establishes_environment_from_scene_location(self):
        coordinator = CinematicIntelligenceCoordinator()
        director_plan, render_plan = _two_shot_plan("proj_env")
        coordinator.enrich_render_plan(director_plan, render_plan)

        environments = coordinator.environments.list_for_project("proj_env")
        assert len(environments) == 1
        assert environments[0]["name"] == "Rooftop at dusk"

    def test_detects_camera_continuity_violations_between_adjacent_shots(self):
        coordinator = CinematicIntelligenceCoordinator()
        director_plan, render_plan = _two_shot_plan("proj_violations")
        coordinator.enrich_render_plan(director_plan, render_plan)

        report = coordinator.get_project_report("proj_violations")
        violation_types = {p["violation_type"] for p in report["problems"] if "violation_type" in p}
        assert "focal_length_jump" in violation_types
        assert "camera_height_jump" in violation_types
        assert "impossible_camera_jump" in violation_types
        assert report["scores"]["camera_consistency"] < 1.0

    def test_no_style_lock_when_no_global_style(self):
        coordinator = CinematicIntelligenceCoordinator()
        director_plan, render_plan = _two_shot_plan("proj_nostyle")
        director_plan["global_style"] = None
        coordinator.enrich_render_plan(director_plan, render_plan)
        assert coordinator.style_lock.exists("proj_nostyle") is False


class TestGetProjectReport:
    def test_object_consistency_none_when_no_objects_tracked(self):
        coordinator = CinematicIntelligenceCoordinator()
        director_plan, render_plan = _compiled_plan_and_render_plan("proj_no_objects")
        coordinator.enrich_render_plan(director_plan, render_plan)

        report = coordinator.get_project_report("proj_no_objects")
        assert report["scores"]["object_consistency"] is None

    def test_object_consistency_perfect_when_objects_tracked_but_no_conflict_detected(self):
        # DirectorPlan/Shot has no object-reference field today (see
        # CinematicIntelligenceCoordinator's docstring) - objects are
        # established manually via the engine, the same "wired and
        # reachable, not auto-detected from free text" pattern Phase 7's
        # own tests use. With no object_location_conflict violations
        # recorded, the score is a perfect 1.0, not None (the object is
        # tracked, it's just never contradicted).
        coordinator = CinematicIntelligenceCoordinator()
        director_plan, render_plan = _two_shot_plan("proj_objects")
        coordinator.objects.establish("proj_objects", "car", object_id="obj_car")
        coordinator.objects.record_location("obj_car", "scene_1", "shot_1", "driveway")
        coordinator.enrich_render_plan(director_plan, render_plan)

        report = coordinator.get_project_report("proj_objects")
        assert report["object_count"] == 1
        assert report["scores"]["object_consistency"] == 1.0

    def test_object_consistency_reflects_recorded_location_conflicts(self):
        # Exercises get_project_report's aggregation math directly against
        # a real ContinuityReport containing an object_location_conflict
        # violation (the shape SceneContinuityEngine._check_objects
        # produces), proving the score genuinely responds to that
        # violation type once one is recorded.
        coordinator = CinematicIntelligenceCoordinator()
        coordinator.objects.establish("proj_objconflict", "car", object_id="obj_car")
        coordinator._continuity_reports["proj_objconflict"] = [
            {
                "scope": "scene",
                "passed": False,
                "violations": [
                    {
                        "violation_type": "object_location_conflict",
                        "severity": "warning",
                        "description": "obj_car conflict",
                        "shot_id": "shot_2",
                    }
                ],
            }
        ]
        report = coordinator.get_project_report("proj_objconflict")
        assert report["scores"]["object_consistency"] == pytest.approx(0.85)

    def test_overall_is_mean_of_present_scores(self):
        coordinator = CinematicIntelligenceCoordinator()
        director_plan, render_plan = _compiled_plan_and_render_plan("proj_overall")
        coordinator.enrich_render_plan(director_plan, render_plan)
        report = coordinator.get_project_report("proj_overall")
        present = [v for k, v in report["scores"].items() if k != "overall" and v is not None]
        assert report["scores"]["overall"] == pytest.approx(sum(present) / len(present), abs=1e-6)

    def test_empty_project_report_has_no_crash_and_null_scores(self):
        coordinator = CinematicIntelligenceCoordinator()
        report = coordinator.get_project_report("proj_never_analyzed")
        assert report["shots_analyzed"] == 0
        assert report["scores"]["overall"] is None
        assert report["problems"] == []
        assert report["repair_suggestions"] == []


class TestImprovePrompt:
    def test_bumps_version_and_uses_prior_context(self):
        coordinator = CinematicIntelligenceCoordinator()
        director_plan, render_plan = _compiled_plan_and_render_plan("proj_improve")
        coordinator.enrich_render_plan(director_plan, render_plan)

        shot_id = render_plan["render_specs"][0]["shot_id"]
        improved = coordinator.improve_prompt("proj_improve", shot_id)
        assert improved["version"] == 2

    def test_raises_for_unknown_shot(self):
        coordinator = CinematicIntelligenceCoordinator()
        with pytest.raises(CinematicIntelligenceCoordinatorError):
            coordinator.improve_prompt("proj_unknown", "shot_unknown")


class TestRepairAndReview:
    def test_repair_shot_requires_prior_quality_report(self):
        coordinator = CinematicIntelligenceCoordinator()
        with pytest.raises(CinematicIntelligenceCoordinatorError):
            coordinator.repair_shot("proj_x", "shot_x")

    def test_full_repair_and_review_flow(self):
        coordinator = CinematicIntelligenceCoordinator()
        director_plan, render_plan = _two_shot_plan("proj_repair_flow")
        coordinator.enrich_render_plan(director_plan, render_plan)

        action = coordinator.repair_shot("proj_repair_flow", "shot_2")
        assert action["shot_id"] == "shot_2"
        assert action["review_status"] == "pending"

        approved = coordinator.review_repair("proj_repair_flow", action["repair_id"], approved=True)
        assert approved["review_status"] == "approved"

        listed = coordinator.list_repairs("proj_repair_flow")
        assert len(listed) == 1
        assert listed[0]["review_status"] == "approved"

    def test_review_unknown_repair_raises(self):
        coordinator = CinematicIntelligenceCoordinator()
        with pytest.raises(CinematicIntelligenceCoordinatorError):
            coordinator.review_repair("proj_x", "repair_unknown", approved=True)

    def test_list_repairs_empty_for_unknown_project(self):
        coordinator = CinematicIntelligenceCoordinator()
        assert coordinator.list_repairs("proj_never_touched") == []
