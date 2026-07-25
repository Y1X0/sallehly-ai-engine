"""EnvironmentConsistencyEngine (services/cinematic-intelligence): keeps
weather/time-of-day/season/architecture/layout coherent for a location
across every scene set there, and catches an accidental "impossible
jump" before it's recorded via detect_drift()."""

from __future__ import annotations

import pytest
from cinematic_intelligence.environment_consistency import (
    EnvironmentConsistencyEngine,
    EnvironmentConsistencyEngineError,
)


def test_establish_records_given_fields():
    engine = EnvironmentConsistencyEngine()
    profile = engine.establish(
        "proj_1",
        "Main Street",
        environment_id="env_street",
        weather="clear",
        time_of_day="morning",
        season="spring",
    )
    assert profile["weather"] == "clear"
    assert profile["time_of_day"] == "morning"
    assert profile["season"] == "spring"


def test_establish_with_reference_image_ids():
    engine = EnvironmentConsistencyEngine()
    profile = engine.establish("proj_1", "Main Street", environment_id="env_street", reference_image_ids=["asset_1"])
    assert profile["reference_image_ids"] == ["asset_1"]


def test_establish_twice_raises():
    engine = EnvironmentConsistencyEngine()
    engine.establish("proj_1", "Main Street", environment_id="env_street")
    with pytest.raises(EnvironmentConsistencyEngineError, match="already exists"):
        engine.establish("proj_1", "Main Street", environment_id="env_street")


def test_get_unknown_raises():
    engine = EnvironmentConsistencyEngine()
    with pytest.raises(EnvironmentConsistencyEngineError, match="No EnvironmentProfile"):
        engine.get("env_unknown")


def test_update_changes_mutable_fields():
    engine = EnvironmentConsistencyEngine()
    engine.establish("proj_1", "Main Street", environment_id="env_street", weather="clear")
    updated = engine.update("env_street", weather="rain")
    assert updated["weather"] == "rain"


def test_update_rejects_fixed_fields():
    engine = EnvironmentConsistencyEngine()
    engine.establish("proj_1", "Main Street", environment_id="env_street")
    with pytest.raises(EnvironmentConsistencyEngineError, match="fixed fields"):
        engine.update("env_street", name="Different Street")


def test_detect_drift_flags_mismatch():
    engine = EnvironmentConsistencyEngine()
    engine.establish("proj_1", "Main Street", environment_id="env_street", weather="clear", time_of_day="morning")

    violations = engine.detect_drift("env_street", {"weather": "rain"})
    assert len(violations) == 1
    assert violations[0]["violation_type"] == "environment_jump"
    assert violations[0]["severity"] == "critical"


def test_detect_drift_no_violation_when_matching():
    engine = EnvironmentConsistencyEngine()
    engine.establish("proj_1", "Main Street", environment_id="env_street", weather="clear")
    assert engine.detect_drift("env_street", {"weather": "clear"}) == []


def test_detect_drift_ignores_fields_not_yet_established():
    engine = EnvironmentConsistencyEngine()
    engine.establish("proj_1", "Main Street", environment_id="env_street")
    assert engine.detect_drift("env_street", {"weather": "rain"}) == []


def test_detect_drift_multiple_fields():
    engine = EnvironmentConsistencyEngine()
    engine.establish(
        "proj_1", "Main Street", environment_id="env_street", weather="clear", time_of_day="morning", sky="blue"
    )
    violations = engine.detect_drift("env_street", {"weather": "snow", "time_of_day": "night", "sky": "grey"})
    assert {v["violation_type"] for v in violations} == {"environment_jump"}
    assert len(violations) == 3


def test_exists():
    engine = EnvironmentConsistencyEngine()
    assert engine.exists("env_street") is False
    engine.establish("proj_1", "Main Street", environment_id="env_street")
    assert engine.exists("env_street") is True


def test_list_for_project():
    engine = EnvironmentConsistencyEngine()
    engine.establish("proj_1", "Main Street", environment_id="env_street")
    engine.establish("proj_2", "Beach", environment_id="env_beach")
    assert [p["environment_id"] for p in engine.list_for_project("proj_1")] == ["env_street"]
