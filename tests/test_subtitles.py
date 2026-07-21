"""Subtitle System (services/post-processing): SRT/WebVTT generation,
styling presets, multilingual tracks. No ffmpeg execution here (pure
string formatting) - burned-in rendering is covered by
test_ffmpeg_compositor.py."""

from __future__ import annotations

import pytest
import schemas
from post_processing import SubtitleGenerator, SubtitleGeneratorError

DIRECTOR_PLAN = {
    "project_id": "proj_sub",
    "scenes": [
        {
            "scene_id": "s1",
            "order": 0,
            "summary": "x",
            "shots": [
                {"shot_id": "sh1", "order": 0, "duration_sec": 3.0, "description": "A watch gleams."},
                {"shot_id": "sh2", "order": 1, "duration_sec": 2.5, "description": "Close up on the dial."},
            ],
        }
    ],
}


def test_generate_from_shots_produces_one_cue_per_shot_in_order():
    track = SubtitleGenerator().generate_from_shots(DIRECTOR_PLAN, language="en")
    assert [c["shot_id"] for c in track["cues"]] == ["sh1", "sh2"]
    assert track["cues"][0]["text"] == "A watch gleams."


def test_generate_from_shots_cue_timing_matches_cumulative_shot_duration():
    track = SubtitleGenerator().generate_from_shots(DIRECTOR_PLAN, language="en")
    assert track["cues"][0]["start_sec"] == 0.0
    assert track["cues"][0]["end_sec"] == 3.0
    assert track["cues"][1]["start_sec"] == 3.0
    assert track["cues"][1]["end_sec"] == 5.5


def test_generate_from_shots_is_schema_valid():
    track = SubtitleGenerator().generate_from_shots(DIRECTOR_PLAN, language="en")
    schemas.validate(track, "subtitle_track")


def test_multilingual_tracks_share_cue_structure_but_differ_by_language():
    generator = SubtitleGenerator()
    en = generator.generate_from_cues("proj_sub", "en", [{"start_sec": 0, "end_sec": 2, "text": "Hello"}])
    ar = generator.generate_from_cues("proj_sub", "ar", [{"start_sec": 0, "end_sec": 2, "text": "مرحبا"}])
    assert en["language"] == "en"
    assert ar["language"] == "ar"
    assert en["track_id"] != ar["track_id"]


def test_unknown_style_preset_raises():
    with pytest.raises(SubtitleGeneratorError, match="Unknown style_preset_id"):
        SubtitleGenerator().generate_from_cues("p", "en", [{"start_sec": 0, "end_sec": 1, "text": "x"}], style_preset_id="nope")


def test_to_srt_format_is_correct():
    generator = SubtitleGenerator()
    track = generator.generate_from_cues(
        "p", "en",
        [
            {"start_sec": 0, "end_sec": 2.5, "text": "Hello world"},
            {"start_sec": 2.5, "end_sec": 5, "text": "Second caption"},
        ],
    )
    srt = generator.to_srt(track)
    assert srt == (
        "1\n"
        "00:00:00,000 --> 00:00:02,500\n"
        "Hello world\n"
        "\n"
        "2\n"
        "00:00:02,500 --> 00:00:05,000\n"
        "Second caption\n"
    )


def test_to_vtt_format_is_correct():
    generator = SubtitleGenerator()
    track = generator.generate_from_cues("p", "en", [{"start_sec": 0, "end_sec": 1.234, "text": "Hi"}])
    vtt = generator.to_vtt(track)
    assert vtt.startswith("WEBVTT\n")
    assert "00:00:00.000 --> 00:00:01.234" in vtt
    assert "Hi" in vtt


def test_srt_timestamp_formatting_handles_hours():
    generator = SubtitleGenerator()
    track = generator.generate_from_cues("p", "en", [{"start_sec": 3661.5, "end_sec": 3662.0, "text": "late"}])
    srt = generator.to_srt(track)
    assert "01:01:01,500 --> 01:01:02,000" in srt


def test_burn_in_force_style_returns_ass_style_string():
    generator = SubtitleGenerator()
    style = generator.burn_in_force_style("bold_yellow")
    assert "FontSize=28" in style
    assert "PrimaryColour=&H0000FFFF" in style


def test_burn_in_force_style_unknown_preset_raises():
    with pytest.raises(SubtitleGeneratorError):
        SubtitleGenerator().burn_in_force_style("nonexistent")
