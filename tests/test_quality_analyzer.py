"""SceneQualityAnalyzer (services/cinematic-intelligence): scores a
shot's identity/camera/lighting/style/composition/prompt/motion quality
from already-computed continuity/style/prompt signals, via IQualityMetric
plugins."""

from __future__ import annotations

import pytest
from cinematic_intelligence.quality_analyzer import SceneQualityAnalyzer, register_defaults
from config_sdk import QUALITY_METRIC_REGISTRY

METRIC_IDS = (
    "identity_consistency",
    "camera_consistency",
    "lighting_consistency",
    "style_consistency",
    "composition_quality",
    "prompt_adherence",
    "motion_quality",
)


@pytest.fixture(autouse=True)
def _register():
    register_defaults()


def test_all_builtin_metrics_registered():
    for metric_id in METRIC_IDS:
        assert metric_id in QUALITY_METRIC_REGISTRY


def test_no_violations_scores_perfect():
    analyzer = SceneQualityAnalyzer()
    report = analyzer.analyze("proj_1", "shot_1")

    for metric_id in METRIC_IDS:
        assert report["scores"][metric_id] == 1.0
    assert report["scores"]["overall"] == 1.0
    assert report["repair_recommended"] is False
    assert report["embeddings_used"] is False
    assert report["issues"] == []


def test_critical_identity_violation_penalizes_identity_score_only():
    analyzer = SceneQualityAnalyzer()
    violations = [{"violation_type": "character_identity_drift", "severity": "critical", "description": "not established"}]
    report = analyzer.analyze("proj_1", "shot_1", scene_violations=violations)

    assert report["scores"]["identity_consistency"] == pytest.approx(0.6)
    assert report["scores"]["camera_consistency"] == 1.0
    assert report["repair_recommended"] is True


def test_camera_violation_penalizes_camera_score():
    analyzer = SceneQualityAnalyzer()
    violations = [{"violation_type": "focal_length_jump", "severity": "warning", "description": "lens jumped"}]
    report = analyzer.analyze("proj_1", "shot_1", camera_violations=violations)

    assert report["scores"]["camera_consistency"] == pytest.approx(0.85)
    assert report["scores"]["identity_consistency"] == 1.0


def test_environment_jump_penalizes_lighting_score():
    analyzer = SceneQualityAnalyzer()
    violations = [{"violation_type": "environment_jump", "severity": "critical", "description": "weather changed"}]
    report = analyzer.analyze("proj_1", "shot_1", scene_violations=violations)

    assert report["scores"]["lighting_consistency"] == pytest.approx(0.6)


def test_style_violation_penalizes_style_score():
    analyzer = SceneQualityAnalyzer()
    violations = [{"violation_type": "style_drift", "severity": "warning", "description": "palette diverged"}]
    report = analyzer.analyze("proj_1", "shot_1", style_violations=violations)

    assert report["scores"]["style_consistency"] == pytest.approx(0.85)


def test_composition_penalized_by_timing_and_entry_exit():
    analyzer = SceneQualityAnalyzer()
    violations = [
        {"violation_type": "timing_gap", "severity": "info", "description": "gap"},
        {"violation_type": "entry_exit_mismatch", "severity": "warning", "description": "mismatch"},
    ]
    report = analyzer.analyze("proj_1", "shot_1", scene_violations=violations)

    assert report["scores"]["composition_quality"] < 1.0


def test_motion_quality_penalized_by_motion_and_camera_direction_flips():
    analyzer = SceneQualityAnalyzer()
    scene_violations = [{"violation_type": "motion_direction_flip", "severity": "warning", "description": "flip"}]
    camera_violations = [{"violation_type": "camera_direction_flip", "severity": "warning", "description": "flip"}]
    report = analyzer.analyze("proj_1", "shot_1", scene_violations=scene_violations, camera_violations=camera_violations)

    assert report["scores"]["motion_quality"] == pytest.approx(0.85)


def test_prompt_adherence_uses_prompt_score():
    analyzer = SceneQualityAnalyzer()
    report = analyzer.analyze(
        "proj_1", "shot_1", prompt_score={"adherence_estimate": 0.42, "length_score": 1, "redundancy_score": 1, "overall": 1}
    )
    assert report["scores"]["prompt_adherence"] == 0.42


def test_prompt_adherence_defaults_to_one_when_no_score_given():
    analyzer = SceneQualityAnalyzer()
    report = analyzer.analyze("proj_1", "shot_1")
    assert report["scores"]["prompt_adherence"] == 1.0


def test_scores_never_go_below_zero():
    analyzer = SceneQualityAnalyzer()
    violations = [
        {"violation_type": "character_identity_drift", "severity": "critical", "description": "x"}
        for _ in range(10)
    ]
    report = analyzer.analyze("proj_1", "shot_1", scene_violations=violations)
    assert report["scores"]["identity_consistency"] == 0.0


def test_repair_recommended_when_overall_below_threshold():
    analyzer = SceneQualityAnalyzer()
    violations = [{"violation_type": "timing_gap", "severity": "info", "description": "x"} for _ in range(20)]
    report = analyzer.analyze("proj_1", "shot_1", scene_violations=violations, repair_threshold=0.99)
    assert report["repair_recommended"] is True


def test_issues_categorized_correctly():
    analyzer = SceneQualityAnalyzer()
    violations = [{"violation_type": "style_drift", "severity": "warning", "description": "diverged"}]
    report = analyzer.analyze("proj_1", "shot_1", style_violations=violations)
    assert report["issues"][0]["category"] == "style"


def test_report_is_schema_valid_and_scoped_to_project_and_shot():
    analyzer = SceneQualityAnalyzer()
    report = analyzer.analyze("proj_1", "shot_5")
    assert report["schema_version"] == "1.0"
    assert report["project_id"] == "proj_1"
    assert report["shot_id"] == "shot_5"
