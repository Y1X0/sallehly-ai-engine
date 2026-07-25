"""StyleLockEngine (services/cinematic-intelligence): locks one global
StyleLock per project and flags a shot's style_override drifting from
it."""

from __future__ import annotations

import pytest
from cinematic_intelligence.style_lock import StyleLockEngine, StyleLockEngineError

BASE_STYLE = {"visual_style": "cinematic photorealistic", "color_grade": {"palette": ["#112233", "#445566"]}}


def test_lock_creates_locked_record():
    engine = StyleLockEngine()
    lock = engine.lock("proj_1", BASE_STYLE, film_stock="35mm film emulation", lighting_language="warm highlights")

    assert lock["locked"] is True
    assert lock["base_style"] == BASE_STYLE
    assert lock["film_stock"] == "35mm film emulation"
    assert lock["depth_of_field_target"] == "medium"


def test_lock_twice_for_same_project_raises():
    engine = StyleLockEngine()
    engine.lock("proj_1", BASE_STYLE)
    with pytest.raises(StyleLockEngineError, match="already has a StyleLock"):
        engine.lock("proj_1", BASE_STYLE)


def test_get_unknown_project_raises():
    engine = StyleLockEngine()
    with pytest.raises(StyleLockEngineError, match="No StyleLock"):
        engine.get("proj_unknown")


def test_exists():
    engine = StyleLockEngine()
    assert engine.exists("proj_1") is False
    engine.lock("proj_1", BASE_STYLE)
    assert engine.exists("proj_1") is True


def test_check_drift_flags_visual_style_change():
    engine = StyleLockEngine()
    engine.lock("proj_1", BASE_STYLE)

    violations = engine.check_drift("proj_1", {"visual_style": "anime"})
    assert len(violations) == 1
    assert violations[0]["violation_type"] == "style_drift"


def test_check_drift_flags_disjoint_palette():
    engine = StyleLockEngine()
    engine.lock("proj_1", BASE_STYLE)

    violations = engine.check_drift("proj_1", {"color_grade": {"palette": ["#ffffff"]}})
    assert any("palette" in v["description"] for v in violations)


def test_check_drift_no_violation_for_matching_style():
    engine = StyleLockEngine()
    engine.lock("proj_1", BASE_STYLE)

    violations = engine.check_drift("proj_1", {"visual_style": "cinematic photorealistic"})
    assert violations == []


def test_check_drift_no_violation_when_override_empty():
    engine = StyleLockEngine()
    engine.lock("proj_1", BASE_STYLE)

    assert engine.check_drift("proj_1", {}) == []


def test_lock_with_grain_and_bloom_and_lens_effects():
    engine = StyleLockEngine()
    lock = engine.lock(
        "proj_1",
        BASE_STYLE,
        grain={"enabled": True, "intensity": "medium"},
        bloom={"enabled": True, "intensity": "subtle"},
        lens_effects=["anamorphic flares"],
    )
    assert lock["grain"]["enabled"] is True
    assert lock["lens_effects"] == ["anamorphic flares"]


def test_invalid_style_lock_fails_validation():
    engine = StyleLockEngine()
    with pytest.raises(StyleLockEngineError, match="failed validation"):
        engine.lock("proj_1", BASE_STYLE, depth_of_field_target="invalid_value")
