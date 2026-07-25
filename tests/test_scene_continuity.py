"""SceneContinuityEngine (services/cinematic-intelligence): compares two
adjacent shots' entry/exit points, eye lines, actor positions, motion
direction, and timing, plus (via other engines) environment/object/
character cross-checks - producing a ContinuityReport."""

from __future__ import annotations

from cinematic_intelligence.character_consistency import CharacterConsistencyEngine
from cinematic_intelligence.environment_consistency import EnvironmentConsistencyEngine
from cinematic_intelligence.object_consistency import ObjectConsistencyEngine
from cinematic_intelligence.scene_continuity import SceneContinuityEngine


def test_clean_transition_passes_with_no_violations():
    engine = SceneContinuityEngine()
    shot_a = {"shot_id": "shot_1", "exit_point": "screen_right"}
    shot_b = {"shot_id": "shot_2", "entry_point": "screen_left"}

    report = engine.check("proj_1", "scene_1", shot_a, shot_b)

    assert report["passed"] is True
    assert report["violations"] == []
    assert report["scope"] == "scene"
    assert report["subject_id"] == "scene_1"


def test_entry_exit_mismatch_flagged():
    engine = SceneContinuityEngine()
    shot_a = {"shot_id": "shot_1", "exit_point": "screen_right"}
    shot_b = {"shot_id": "shot_2", "entry_point": "door"}

    report = engine.check("proj_1", "scene_1", shot_a, shot_b)

    assert any(v["violation_type"] == "entry_exit_mismatch" for v in report["violations"])


def test_matching_named_exit_and_entry_is_compatible():
    engine = SceneContinuityEngine()
    shot_a = {"shot_id": "shot_1", "exit_point": "door"}
    shot_b = {"shot_id": "shot_2", "entry_point": "door"}

    report = engine.check("proj_1", "scene_1", shot_a, shot_b)
    assert report["violations"] == []


def test_eye_line_mismatch_flagged_when_static():
    engine = SceneContinuityEngine()
    shot_a = {"shot_id": "shot_1", "eye_line": "screen_left"}
    shot_b = {"shot_id": "shot_2", "eye_line": "screen_right", "motion_direction": "static"}

    report = engine.check("proj_1", "scene_1", shot_a, shot_b)
    assert any(v["violation_type"] == "eye_line_mismatch" for v in report["violations"])


def test_eye_line_change_ok_when_motion_explains_it():
    engine = SceneContinuityEngine()
    shot_a = {"shot_id": "shot_1", "eye_line": "screen_left"}
    shot_b = {"shot_id": "shot_2", "eye_line": "screen_right", "motion_direction": "left_to_right"}

    report = engine.check("proj_1", "scene_1", shot_a, shot_b)
    assert not any(v["violation_type"] == "eye_line_mismatch" for v in report["violations"])


def test_actor_position_jump_flagged_when_static():
    engine = SceneContinuityEngine()
    shot_a = {"shot_id": "shot_1", "actor_positions": {"char_alice": "left"}}
    shot_b = {"shot_id": "shot_2", "actor_positions": {"char_alice": "right"}, "motion_direction": "static"}

    report = engine.check("proj_1", "scene_1", shot_a, shot_b)
    violations = [v for v in report["violations"] if v["violation_type"] == "actor_position_jump"]
    assert len(violations) == 1


def test_motion_direction_flip_flagged():
    engine = SceneContinuityEngine()
    shot_a = {"shot_id": "shot_1", "motion_direction": "left_to_right"}
    shot_b = {"shot_id": "shot_2", "motion_direction": "right_to_left"}

    report = engine.check("proj_1", "scene_1", shot_a, shot_b)
    assert any(v["violation_type"] == "motion_direction_flip" for v in report["violations"])


def test_motion_direction_same_is_not_a_flip():
    engine = SceneContinuityEngine()
    shot_a = {"shot_id": "shot_1", "motion_direction": "left_to_right"}
    shot_b = {"shot_id": "shot_2", "motion_direction": "left_to_right"}

    report = engine.check("proj_1", "scene_1", shot_a, shot_b)
    assert report["violations"] == []


def test_timing_gap_flagged():
    engine = SceneContinuityEngine()
    shot_a = {"shot_id": "shot_1", "timing_sec": 0.0, "duration_sec": 3.0}
    shot_b = {"shot_id": "shot_2", "timing_sec": 5.0}

    report = engine.check("proj_1", "scene_1", shot_a, shot_b)
    violations = [v for v in report["violations"] if v["violation_type"] == "timing_gap"]
    assert len(violations) == 1
    assert violations[0]["severity"] == "info"


def test_timing_overlap_flagged():
    engine = SceneContinuityEngine()
    shot_a = {"shot_id": "shot_1", "timing_sec": 0.0, "duration_sec": 3.0}
    shot_b = {"shot_id": "shot_2", "timing_sec": 1.0}

    report = engine.check("proj_1", "scene_1", shot_a, shot_b)
    assert any(v["violation_type"] == "timing_gap" for v in report["violations"])


def test_timing_within_tolerance_not_flagged():
    engine = SceneContinuityEngine()
    shot_a = {"shot_id": "shot_1", "timing_sec": 0.0, "duration_sec": 3.0}
    shot_b = {"shot_id": "shot_2", "timing_sec": 3.2}

    report = engine.check("proj_1", "scene_1", shot_a, shot_b, max_timing_gap_sec=0.5)
    assert report["violations"] == []


def test_environment_jump_detected_via_environment_engine():
    env_engine = EnvironmentConsistencyEngine()
    env_engine.establish("proj_1", "Main Street", environment_id="env_street", weather="clear")
    engine = SceneContinuityEngine()

    shot_a = {"shot_id": "shot_1", "environment_id": "env_street"}
    shot_b = {"shot_id": "shot_2", "environment_id": "env_street", "weather": "rain"}

    report = engine.check("proj_1", "scene_1", shot_a, shot_b, environment_engine=env_engine)
    assert any(v["violation_type"] == "environment_jump" for v in report["violations"])
    assert report["passed"] is False


def test_environment_not_established_produces_no_violation():
    env_engine = EnvironmentConsistencyEngine()
    engine = SceneContinuityEngine()

    shot_a = {"shot_id": "shot_1"}
    shot_b = {"shot_id": "shot_2", "environment_id": "env_never_established", "weather": "rain"}

    report = engine.check("proj_1", "scene_1", shot_a, shot_b, environment_engine=env_engine)
    assert report["violations"] == []


def test_object_not_established_produces_no_violation():
    obj_engine = ObjectConsistencyEngine()
    engine = SceneContinuityEngine()

    shot_a = {"shot_id": "shot_1"}
    shot_b = {"shot_id": "shot_2", "object_locations": {"obj_never_established": "garage"}}

    report = engine.check("proj_1", "scene_1", shot_a, shot_b, object_engine=obj_engine)
    assert report["violations"] == []


def test_object_location_conflict_detected_via_object_engine():
    obj_engine = ObjectConsistencyEngine()
    obj_engine.establish("proj_1", "car", object_id="obj_car")
    obj_engine.record_location("obj_car", "scene_1", "shot_1", "driveway")
    engine = SceneContinuityEngine()

    shot_a = {"shot_id": "shot_1"}
    shot_b = {"shot_id": "shot_2", "object_locations": {"obj_car": "garage"}}

    report = engine.check("proj_1", "scene_1", shot_a, shot_b, object_engine=obj_engine)
    assert any(v["violation_type"] == "object_location_conflict" for v in report["violations"])


def test_character_identity_drift_when_unestablished():
    char_engine = CharacterConsistencyEngine()
    engine = SceneContinuityEngine()

    shot_a = {"shot_id": "shot_1"}
    shot_b = {"shot_id": "shot_2", "character_ids": ["char_unestablished"]}

    report = engine.check("proj_1", "scene_1", shot_a, shot_b, character_engine=char_engine)
    violations = [v for v in report["violations"] if v["violation_type"] == "character_identity_drift"]
    assert len(violations) == 1
    assert violations[0]["severity"] == "critical"
    assert report["passed"] is False


def test_no_identity_drift_when_character_established():
    char_engine = CharacterConsistencyEngine()
    char_engine.establish(
        "proj_1",
        "Alice",
        {"face_description": "oval", "age_range": "adult", "skin_tone": "tan"},
        character_id="char_alice",
    )
    engine = SceneContinuityEngine()

    shot_a = {"shot_id": "shot_1"}
    shot_b = {"shot_id": "shot_2", "character_ids": ["char_alice"]}

    report = engine.check("proj_1", "scene_1", shot_a, shot_b, character_engine=char_engine)
    assert report["violations"] == []
