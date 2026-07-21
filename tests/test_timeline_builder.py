"""TimelineBuilder (services/post-processing): sequences a project's
per-shot RawClips into a Timeline, honoring Shot.transition_in/
transition_out. No ffmpeg required - pure data transformation, schema-
validated."""

from __future__ import annotations

import pytest
from post_processing import TimelineBuilder, TimelineBuilderError

DIRECTOR_PLAN = {
    "project_id": "proj_tl",
    "aspect_ratio": "16:9",
    "scenes": [
        {
            "scene_id": "scene_1",
            "order": 0,
            "summary": "opening",
            "shots": [
                {
                    "shot_id": "shot_1",
                    "order": 0,
                    "duration_sec": 3.0,
                    "description": "wide establishing shot",
                    "transition_in": "fade_from_black",
                    "transition_out": "cut",
                },
                {
                    "shot_id": "shot_2",
                    "order": 1,
                    "duration_sec": 2.5,
                    "description": "medium shot",
                    "transition_in": "cut",
                    "transition_out": "dissolve",
                },
            ],
        },
        {
            "scene_id": "scene_2",
            "order": 1,
            "summary": "closing",
            "shots": [
                {
                    "shot_id": "shot_3",
                    "order": 0,
                    "duration_sec": 2.0,
                    "description": "close up",
                    "transition_in": "cut",
                    "transition_out": "fade_to_black",
                },
            ],
        },
    ],
}

ASSETS = {
    "shot_1": {"versions": [{"uri": "file:///tmp/shot_1.mp4"}]},
    "shot_2": {"versions": [{"uri": "file:///tmp/shot_2.mp4"}]},
    "shot_3": {"versions": [{"uri": "file:///tmp/shot_3.mp4"}]},
}


def test_build_orders_clips_across_scenes():
    timeline = TimelineBuilder().build(DIRECTOR_PLAN, ASSETS)
    shot_ids = [clip["shot_id"] for clip in timeline["video_clips"]]
    assert shot_ids == ["shot_1", "shot_2", "shot_3"]


def test_build_maps_shot_transitions_onto_transition_types():
    timeline = TimelineBuilder().build(DIRECTOR_PLAN, ASSETS)
    clips = {clip["shot_id"]: clip for clip in timeline["video_clips"]}

    assert clips["shot_1"]["transition_in"]["type"] == "fade_in"
    assert "transition_in" not in clips["shot_2"]  # "cut" carries no special effect
    assert clips["shot_2"]["transition_out"]["type"] == "dissolve"
    assert clips["shot_3"]["transition_out"]["type"] == "fade_out"


def test_build_computes_total_duration():
    timeline = TimelineBuilder().build(DIRECTOR_PLAN, ASSETS)
    assert timeline["total_duration_sec"] == pytest.approx(7.5)


def test_build_defaults_resolution_from_aspect_ratio_when_no_render_plan():
    timeline = TimelineBuilder().build(DIRECTOR_PLAN, ASSETS)
    assert timeline["resolution"] == "1920x1080"
    assert timeline["fps"] == 24


def test_build_infers_fps_and_resolution_from_render_plan():
    render_plan = {"render_specs": [{"fps": 30, "resolution": "1280x720"}]}
    timeline = TimelineBuilder().build(DIRECTOR_PLAN, ASSETS, render_plan=render_plan)
    assert timeline["fps"] == 30
    assert timeline["resolution"] == "1280x720"


def test_build_raises_when_a_shot_has_no_video_asset():
    with pytest.raises(TimelineBuilderError, match="shot_2"):
        TimelineBuilder().build(DIRECTOR_PLAN, {"shot_1": ASSETS["shot_1"], "shot_3": ASSETS["shot_3"]})


def test_build_produces_schema_valid_timeline():
    import schemas

    timeline = TimelineBuilder().build(DIRECTOR_PLAN, ASSETS)
    schemas.validate(timeline, "timeline")
