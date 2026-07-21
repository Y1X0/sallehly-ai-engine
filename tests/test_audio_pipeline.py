"""Audio Pipeline (services/post-processing): adding tracks to a
Timeline and compiling the ffmpeg audio filtergraph fragment. No ffmpeg
execution here (structural/string assertions) - real execution is
covered by test_ffmpeg_compositor.py's audio-mix tests."""

from __future__ import annotations

import re

import schemas
from post_processing import AudioPipeline

BASE_TIMELINE = {
    "schema_version": "1.0",
    "project_id": "proj_audio",
    "fps": 24,
    "resolution": "1920x1080",
    "video_clips": [{"clip_id": "c1", "shot_id": "s1", "source_uri": "file:///tmp/s1.mp4", "duration_sec": 5.0}],
}


def test_add_track_appends_and_stays_schema_valid():
    pipeline = AudioPipeline()
    timeline = pipeline.add_track(BASE_TIMELINE, "music", "file:///tmp/music.mp3", start_time_sec=0, duration_sec=5)
    schemas.validate(timeline, "timeline")
    assert len(timeline["audio_tracks"]) == 1
    assert timeline["audio_tracks"][0]["kind"] == "music"


def test_add_track_does_not_mutate_the_input_timeline():
    pipeline = AudioPipeline()
    pipeline.add_track(BASE_TIMELINE, "sfx", "file:///tmp/sfx.mp3", start_time_sec=1)
    assert "audio_tracks" not in BASE_TIMELINE


def test_multiple_tracks_of_different_kinds():
    pipeline = AudioPipeline()
    timeline = pipeline.add_track(BASE_TIMELINE, "music", "file:///tmp/music.mp3", start_time_sec=0)
    timeline = pipeline.add_track(timeline, "voiceover", "file:///tmp/vo.mp3", start_time_sec=1)
    timeline = pipeline.add_track(timeline, "sfx", "file:///tmp/sfx.mp3", start_time_sec=2)
    kinds = [t["kind"] for t in timeline["audio_tracks"]]
    assert kinds == ["music", "voiceover", "sfx"]


def test_build_mix_filter_returns_none_for_no_tracks():
    assert AudioPipeline().build_mix_filter([], {}) is None


def test_build_mix_filter_single_track_no_amix():
    pipeline = AudioPipeline()
    timeline = pipeline.add_track(BASE_TIMELINE, "music", "file:///tmp/music.mp3", start_time_sec=0, volume_db=-3)
    track = timeline["audio_tracks"][0]
    filt, label = pipeline.build_mix_filter([track], {track["track_id"]: 1})
    assert "amix" not in filt
    assert filt.startswith("[1:a]")
    assert label in filt


def test_build_mix_filter_multiple_tracks_uses_amix():
    pipeline = AudioPipeline()
    timeline = pipeline.add_track(BASE_TIMELINE, "music", "file:///tmp/music.mp3", start_time_sec=0)
    timeline = pipeline.add_track(timeline, "voiceover", "file:///tmp/vo.mp3", start_time_sec=1)
    tracks = timeline["audio_tracks"]
    idx_map = {t["track_id"]: i + 1 for i, t in enumerate(tracks)}
    filt, label = pipeline.build_mix_filter(tracks, idx_map)
    assert "amix=inputs=2" in filt
    assert label == "aout"


def test_build_mix_filter_applies_delay_for_nonzero_start_time():
    pipeline = AudioPipeline()
    timeline = pipeline.add_track(BASE_TIMELINE, "voiceover", "file:///tmp/vo.mp3", start_time_sec=2.5)
    track = timeline["audio_tracks"][0]
    filt, _ = pipeline.build_mix_filter([track], {track["track_id"]: 1})
    assert "adelay=2500|2500" in filt


def test_build_mix_filter_applies_fades():
    pipeline = AudioPipeline()
    timeline = pipeline.add_track(
        BASE_TIMELINE, "music", "file:///tmp/music.mp3", start_time_sec=0, duration_sec=5,
        fade_in_sec=1.0, fade_out_sec=1.5,
    )
    track = timeline["audio_tracks"][0]
    filt, _ = pipeline.build_mix_filter([track], {track["track_id"]: 1})
    assert "afade=t=in:st=0:d=1.0" in filt
    assert "afade=t=out:st=3.5:d=1.5" in filt


def test_volume_automation_produces_a_valid_piecewise_expression():
    pipeline = AudioPipeline()
    timeline = pipeline.add_track(
        BASE_TIMELINE, "music", "file:///tmp/music.mp3", start_time_sec=0,
        volume_automation=[{"t": 0, "volume_db": -30}, {"t": 2, "volume_db": -6}, {"t": 4, "volume_db": -30}],
    )
    track = timeline["audio_tracks"][0]
    filt, _ = pipeline.build_mix_filter([track], {track["track_id"]: 1})
    # A well-formed ffmpeg expression: balanced parens, only if/lt/t and numbers.
    expr = re.search(r"volume=([^:]+):eval=frame", filt).group(1)
    assert expr.count("(") == expr.count(")")
    assert expr.startswith("if(lt(t,")
    # Silence at both ends (roughly -30dB -> linear ~0.0316), peak in the middle (-6dB -> ~0.501).
    assert "0.031623" in expr or "0.031623" in expr.replace(" ", "")
    assert "0.501187" in expr


def test_volume_automation_keyframes_must_still_produce_valid_timeline():
    pipeline = AudioPipeline()
    timeline = pipeline.add_track(
        BASE_TIMELINE, "music", "file:///tmp/music.mp3", start_time_sec=0,
        volume_automation=[{"t": 0, "volume_db": -10}],
    )
    schemas.validate(timeline, "timeline")
