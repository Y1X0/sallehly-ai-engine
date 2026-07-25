"""CameraContinuityEngine (services/cinematic-intelligence): compares two
adjacent shots' lens/height/movement/framing and reports discontinuities
that would read as an impossible or jarring camera jump."""

from __future__ import annotations

from cinematic_intelligence.camera_continuity import CameraContinuityEngine


def _shot(shot_id, **camera_kwargs):
    return {"shot_id": shot_id, "camera": camera_kwargs}


def test_similar_shots_pass_with_no_violations():
    engine = CameraContinuityEngine()
    shot_a = _shot("shot_1", shot_type="medium", focal_length_mm_equiv=35, angle="eye_level", movement={"type": "static"})
    shot_b = _shot("shot_2", shot_type="medium_close_up", focal_length_mm_equiv=50, angle="eye_level", movement={"type": "static"})

    report = engine.check("proj_1", shot_a, shot_b)

    assert report["passed"] is True
    assert report["violations"] == []
    assert report["scope"] == "camera"
    assert report["subject_id"] == "shot_1->shot_2"


def test_focal_length_warning_threshold():
    engine = CameraContinuityEngine()
    shot_a = _shot("shot_1", focal_length_mm_equiv=24)
    shot_b = _shot("shot_2", focal_length_mm_equiv=110)

    report = engine.check("proj_1", shot_a, shot_b)
    violations = [v for v in report["violations"] if v["violation_type"] == "focal_length_jump"]
    assert violations[0]["severity"] == "warning"


def test_focal_length_critical_threshold():
    engine = CameraContinuityEngine()
    shot_a = _shot("shot_1", focal_length_mm_equiv=24)
    shot_b = _shot("shot_2", focal_length_mm_equiv=300)

    report = engine.check("proj_1", shot_a, shot_b)
    violations = [v for v in report["violations"] if v["violation_type"] == "focal_length_jump"]
    assert violations[0]["severity"] == "critical"
    assert report["passed"] is False


def test_camera_height_jump_flagged():
    engine = CameraContinuityEngine()
    shot_a = _shot("shot_1", angle="birds_eye")
    shot_b = _shot("shot_2", angle="low_angle")

    report = engine.check("proj_1", shot_a, shot_b)
    assert any(v["violation_type"] == "camera_height_jump" for v in report["violations"])
    assert report["passed"] is False


def test_adjacent_angles_not_flagged():
    engine = CameraContinuityEngine()
    shot_a = _shot("shot_1", angle="eye_level")
    shot_b = _shot("shot_2", angle="dutch_tilt")

    report = engine.check("proj_1", shot_a, shot_b)
    assert not any(v["violation_type"] == "camera_height_jump" for v in report["violations"])


def test_camera_direction_flip_flagged():
    engine = CameraContinuityEngine()
    shot_a = _shot("shot_1", movement={"type": "dolly_in"})
    shot_b = _shot("shot_2", movement={"type": "dolly_out"})

    report = engine.check("proj_1", shot_a, shot_b)
    violations = [v for v in report["violations"] if v["violation_type"] == "camera_direction_flip"]
    assert len(violations) == 1
    assert violations[0]["severity"] == "warning"


def test_impossible_camera_jump_flagged():
    engine = CameraContinuityEngine()
    shot_a = _shot("shot_1", shot_type="extreme_wide", angle="birds_eye")
    shot_b = _shot("shot_2", shot_type="extreme_close_up", angle="low_angle")

    report = engine.check("proj_1", shot_a, shot_b)
    assert any(v["violation_type"] == "impossible_camera_jump" for v in report["violations"])


def test_impossible_camera_jump_not_flagged_without_angle_change():
    engine = CameraContinuityEngine()
    shot_a = _shot("shot_1", shot_type="extreme_wide", angle="eye_level")
    shot_b = _shot("shot_2", shot_type="extreme_close_up", angle="eye_level")

    report = engine.check("proj_1", shot_a, shot_b)
    assert not any(v["violation_type"] == "impossible_camera_jump" for v in report["violations"])


def test_shot_rhythm_break_flagged():
    engine = CameraContinuityEngine()
    shot_a = {"shot_id": "shot_1", "camera": {}}
    shot_b = {"shot_id": "shot_2", "camera": {}, "duration_sec": 12.0}

    report = engine.check("proj_1", shot_a, shot_b, scene_avg_duration_sec=3.0)
    violations = [v for v in report["violations"] if v["violation_type"] == "shot_rhythm_break"]
    assert len(violations) == 1
    assert violations[0]["severity"] == "info"


def test_shot_rhythm_not_flagged_when_close_to_average():
    engine = CameraContinuityEngine()
    shot_a = {"shot_id": "shot_1", "camera": {}}
    shot_b = {"shot_id": "shot_2", "camera": {}, "duration_sec": 3.2}

    report = engine.check("proj_1", shot_a, shot_b, scene_avg_duration_sec=3.0)
    assert report["violations"] == []


def test_shot_rhythm_skipped_when_duration_missing():
    engine = CameraContinuityEngine()
    shot_a = {"shot_id": "shot_1", "camera": {}}
    shot_b = {"shot_id": "shot_2", "camera": {}}

    report = engine.check("proj_1", shot_a, shot_b, scene_avg_duration_sec=3.0)
    assert report["violations"] == []


def test_missing_camera_data_produces_no_false_positives():
    engine = CameraContinuityEngine()
    shot_a = {"shot_id": "shot_1"}
    shot_b = {"shot_id": "shot_2"}

    report = engine.check("proj_1", shot_a, shot_b)
    assert report["passed"] is True
    assert report["violations"] == []
