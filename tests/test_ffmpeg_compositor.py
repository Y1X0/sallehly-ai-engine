"""FfmpegCompositor (services/post-processing): real ffmpeg execution -
every test here actually runs ffmpeg and inspects the resulting file
(via ffprobe duration/streams, or by sampling real rendered pixels).
Skipped if ffmpeg isn't installed - see docs/DEV_SETUP.md."""

from __future__ import annotations

import pytest
from media_helpers import FFMPEG_AVAILABLE, make_color_clip, make_tone, sample_pixel
from post_processing import register_defaults
from post_processing.compositor import FfmpegCompositor, subtitle_track_from_dict, timeline_from_dict
from post_processing.ffmpeg_utils import probe
from post_processing.subtitle_generator import SubtitleGenerator

pytestmark = pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg not installed - see docs/DEV_SETUP.md")


@pytest.fixture(autouse=True)
def _register_builtins():
    register_defaults()


def test_hard_cut_concatenation_produces_full_combined_duration(tmp_path):
    clip_a = make_color_clip(tmp_path / "a.mp4", "red", duration=2.0)
    clip_b = make_color_clip(tmp_path / "b.mp4", "blue", duration=2.0)
    timeline = timeline_from_dict(
        {
            "schema_version": "1.0",
            "project_id": "p",
            "fps": 24,
            "resolution": "320x240",
            "video_clips": [
                {"clip_id": "c1", "shot_id": "s1", "source_uri": clip_a, "duration_sec": 2.0},
                {"clip_id": "c2", "shot_id": "s2", "source_uri": clip_b, "duration_sec": 2.0},
            ],
        }
    )
    result = FfmpegCompositor().compose(timeline, tmp_path / "out.mp4")
    assert result.duration_sec == pytest.approx(4.0, abs=0.15)

    # a hard cut: red for the first half, blue for the second - no blending at the cut point.
    assert sample_pixel(tmp_path / "out.mp4", 1.0) == (254, 0, 0) or sample_pixel(tmp_path / "out.mp4", 1.0)[0] > 200
    assert sample_pixel(tmp_path / "out.mp4", 3.0)[2] > 200


def test_dissolve_transition_shortens_total_duration_by_the_overlap(tmp_path):
    clip_a = make_color_clip(tmp_path / "a.mp4", "red", duration=2.0)
    clip_b = make_color_clip(tmp_path / "b.mp4", "blue", duration=2.0)
    timeline = timeline_from_dict(
        {
            "schema_version": "1.0",
            "project_id": "p",
            "fps": 24,
            "resolution": "320x240",
            "video_clips": [
                {
                    "clip_id": "c1",
                    "shot_id": "s1",
                    "source_uri": clip_a,
                    "duration_sec": 2.0,
                    "transition_out": {"type": "dissolve", "duration_sec": 0.5},
                },
                {"clip_id": "c2", "shot_id": "s2", "source_uri": clip_b, "duration_sec": 2.0},
            ],
        }
    )
    result = FfmpegCompositor().compose(timeline, tmp_path / "out.mp4")
    # total = 2 + 2 - 0.5 overlap = 3.5s
    assert result.duration_sec == pytest.approx(3.5, abs=0.15)


def test_fade_in_from_black_darkens_the_opening_frames(tmp_path):
    clip = make_color_clip(tmp_path / "a.mp4", "red", duration=2.0)
    timeline = timeline_from_dict(
        {
            "schema_version": "1.0",
            "project_id": "p",
            "fps": 24,
            "resolution": "320x240",
            "video_clips": [
                {
                    "clip_id": "c1",
                    "shot_id": "s1",
                    "source_uri": clip,
                    "duration_sec": 2.0,
                    "transition_in": {"type": "fade_in", "duration_sec": 0.5},
                }
            ],
        }
    )
    FfmpegCompositor().compose(timeline, tmp_path / "out.mp4")

    early_frame = sample_pixel(tmp_path / "out.mp4", 0.02)
    late_frame = sample_pixel(tmp_path / "out.mp4", 1.5)
    assert early_frame[0] < late_frame[0]  # darker (closer to black) near the very start than later
    assert late_frame[0] > 200  # fully red by 1.5s, well past the 0.5s fade


def test_audio_track_is_mixed_into_the_output(tmp_path):
    clip = make_color_clip(tmp_path / "a.mp4", "green", duration=2.0)
    tone = make_tone(tmp_path / "music.aac", duration=2.0)
    timeline_dict = {
        "schema_version": "1.0",
        "project_id": "p",
        "fps": 24,
        "resolution": "320x240",
        "video_clips": [{"clip_id": "c1", "shot_id": "s1", "source_uri": clip, "duration_sec": 2.0}],
        "audio_tracks": [
            {"track_id": "a1", "kind": "music", "source_uri": tone, "start_time_sec": 0.0, "duration_sec": 2.0}
        ],
    }
    output_path = tmp_path / "out.mp4"
    FfmpegCompositor().compose(timeline_from_dict(timeline_dict), output_path)

    probed = probe(output_path)
    audio_streams = [s for s in probed["streams"] if s["codec_type"] == "audio"]
    assert len(audio_streams) == 1
    assert audio_streams[0]["codec_name"] == "aac"


def test_no_audio_tracks_produces_a_video_only_output(tmp_path):
    clip = make_color_clip(tmp_path / "a.mp4", "green", duration=1.0)
    timeline = timeline_from_dict(
        {
            "schema_version": "1.0",
            "project_id": "p",
            "fps": 24,
            "resolution": "320x240",
            "video_clips": [{"clip_id": "c1", "shot_id": "s1", "source_uri": clip, "duration_sec": 1.0}],
        }
    )
    output_path = tmp_path / "out.mp4"
    FfmpegCompositor().compose(timeline, output_path)
    probed = probe(output_path)
    assert not any(s["codec_type"] == "audio" for s in probed["streams"])


def test_burned_in_subtitles_render_visible_text(tmp_path):
    clip = make_color_clip(tmp_path / "a.mp4", "red", duration=2.0)
    timeline = timeline_from_dict(
        {
            "schema_version": "1.0",
            "project_id": "p",
            "fps": 24,
            "resolution": "320x240",
            "video_clips": [{"clip_id": "c1", "shot_id": "s1", "source_uri": clip, "duration_sec": 2.0}],
        }
    )
    sub_dict = SubtitleGenerator().generate_from_cues(
        "p", "en", [{"start_sec": 0, "end_sec": 2, "text": "Hello World"}], style_preset_id="bold_yellow"
    )
    output_path = tmp_path / "out.mp4"
    FfmpegCompositor().compose(timeline, output_path, subtitle_track=subtitle_track_from_dict(sub_dict))

    from media_helpers import count_color_pixels

    yellow, total = count_color_pixels(
        output_path, timestamp_sec=1.0, predicate=lambda r, g, b: r > 180 and g > 180 and b < 100
    )
    assert yellow > 0, "expected some yellow (bold_yellow preset) subtitle pixels in the frame"
