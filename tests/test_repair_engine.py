"""AutomaticRepairEngine (services/cinematic-intelligence): routes a
QualityReport's worst-scoring dimension to the matching IRepairStrategy,
always scoped to exactly one shot - never regenerates the whole project."""

from __future__ import annotations

import pytest
from cinematic_intelligence.quality_analyzer import SceneQualityAnalyzer
from cinematic_intelligence.quality_analyzer import register_defaults as register_metrics
from cinematic_intelligence.repair import (
    AutomaticRepairEngine,
    CameraRepairStrategy,
    IdentityRepairStrategy,
    LightingRepairStrategy,
    PromptRepairStrategy,
    StyleRepairStrategy,
    register_defaults,
)
from config_sdk import REPAIR_STRATEGY_REGISTRY

REPAIR_TYPES = ("prompt_repair", "camera_repair", "style_repair", "identity_repair", "lighting_repair")


@pytest.fixture(autouse=True)
def _register():
    register_metrics()
    register_defaults()


def _report_with_worst(metric_id: str, others_perfect: bool = True) -> dict:
    analyzer = SceneQualityAnalyzer()
    kwargs = {}
    if metric_id == "identity_consistency":
        kwargs["scene_violations"] = [
            {"violation_type": "character_identity_drift", "severity": "critical", "description": "x"}
        ]
    elif metric_id == "camera_consistency":
        kwargs["camera_violations"] = [{"violation_type": "focal_length_jump", "severity": "critical", "description": "x"}]
    elif metric_id == "style_consistency":
        kwargs["style_violations"] = [{"violation_type": "style_drift", "severity": "critical", "description": "x"}]
    elif metric_id == "lighting_consistency":
        kwargs["scene_violations"] = [{"violation_type": "environment_jump", "severity": "critical", "description": "x"}]
    return analyzer.analyze("proj_1", "shot_1", **kwargs)


def test_all_builtin_strategies_registered():
    for repair_type in REPAIR_TYPES:
        assert repair_type in REPAIR_STRATEGY_REGISTRY


def test_routes_identity_worst_score_to_identity_repair():
    engine = AutomaticRepairEngine()
    report = _report_with_worst("identity_consistency")
    action = engine.repair(report, context={"character_profile": {"reference_image_ids": ["a1"], "consistency_seed": 7}})

    assert action["repair_type"] == "identity_repair"
    assert action["status"] == "applied"
    assert action["shot_id"] == "shot_1"
    assert action["quality_report_id"] == report["report_id"]


def test_routes_camera_worst_score_to_camera_repair():
    engine = AutomaticRepairEngine()
    report = _report_with_worst("camera_consistency")
    action = engine.repair(report, context={"last_known_good_camera": {"shot_type": "wide"}, "current_camera": {"shot_type": "close_up"}})

    assert action["repair_type"] == "camera_repair"
    assert action["status"] == "applied"


def test_routes_style_worst_score_to_style_repair():
    engine = AutomaticRepairEngine()
    report = _report_with_worst("style_consistency")
    action = engine.repair(report, context={"style_lock_base_style": {"visual_style": "cinematic"}})

    assert action["repair_type"] == "style_repair"
    assert action["status"] == "applied"


def test_routes_lighting_worst_score_to_lighting_repair():
    engine = AutomaticRepairEngine()
    report = _report_with_worst("lighting_consistency")
    action = engine.repair(report, context={"environment_profile": {"time_of_day": "dusk", "weather": "clear"}})

    assert action["repair_type"] == "lighting_repair"
    assert action["status"] == "applied"


def test_prompt_repair_strategy_requires_context():
    engine = AutomaticRepairEngine()
    report = SceneQualityAnalyzer().analyze(
        "proj_1", "shot_1", scene_violations=[{"violation_type": "timing_gap", "severity": "warning", "description": "x"}] * 5
    )
    action = engine.repair(report, context={})
    assert action["status"] == "failed"


def test_prompt_repair_strategy_applied_when_context_given():
    engine = AutomaticRepairEngine()
    report = SceneQualityAnalyzer().analyze(
        "proj_1", "shot_1", scene_violations=[{"violation_type": "timing_gap", "severity": "warning", "description": "x"}] * 5
    )
    action = engine.repair(report, context={"current_positive_prompt": "Alice walks in"})
    assert action["repair_type"] == "prompt_repair"
    assert action["status"] == "applied"
    assert "Alice walks in" in action["after_summary"]


def test_camera_repair_fails_without_last_known_good():
    engine = AutomaticRepairEngine()
    report = _report_with_worst("camera_consistency")
    action = engine.repair(report, context={})
    assert action["status"] == "failed"


def test_style_repair_fails_without_base_style():
    engine = AutomaticRepairEngine()
    report = _report_with_worst("style_consistency")
    action = engine.repair(report, context={})
    assert action["status"] == "failed"


def test_lighting_repair_fails_without_environment_profile():
    engine = AutomaticRepairEngine()
    report = _report_with_worst("lighting_consistency")
    action = engine.repair(report, context={})
    assert action["status"] == "failed"


def test_identity_repair_fails_without_character_profile():
    engine = AutomaticRepairEngine()
    report = _report_with_worst("identity_consistency")
    action = engine.repair(report, context={})
    assert action["status"] == "failed"


def test_repair_action_is_schema_valid():
    engine = AutomaticRepairEngine()
    report = _report_with_worst("identity_consistency")
    action = engine.repair(report, context={"character_profile": {"reference_image_ids": [], "consistency_seed": None}})
    assert action["schema_version"] == "1.0"
    assert action["repair_id"].startswith("repair_")


def test_repair_never_touches_other_shots():
    engine = AutomaticRepairEngine()
    report = _report_with_worst("identity_consistency")
    action = engine.repair(report, context={"character_profile": {"reference_image_ids": ["a1"]}})
    assert action["shot_id"] == report["shot_id"] == "shot_1"


class TestStrategiesDirectly:
    def test_prompt_repair_strategy_repair_type(self):
        assert PromptRepairStrategy.repair_type == "prompt_repair"

    def test_camera_repair_strategy_repair_type(self):
        assert CameraRepairStrategy.repair_type == "camera_repair"

    def test_style_repair_strategy_repair_type(self):
        assert StyleRepairStrategy.repair_type == "style_repair"

    def test_identity_repair_strategy_repair_type(self):
        assert IdentityRepairStrategy.repair_type == "identity_repair"

    def test_lighting_repair_strategy_repair_type(self):
        assert LightingRepairStrategy.repair_type == "lighting_repair"
