"""Real ffmpeg-backed tests for eval/quality_metrics.py - the tool that
turns the by-hand pixel check that first caught the flat/muddy Kaggle
garbage-frame bug (runs 30303715804, 30316220351) into a repeatable
gate. Uses this repo's own real-media test fixtures
(tests/media_helpers.py), same convention as the post-production
pipeline tests: real ffmpeg execution, never mocked.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from media_helpers import FFMPEG_AVAILABLE, make_color_clip  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval"))
from quality_metrics import FLAT_FRAME_STDDEV_THRESHOLD, analyze_video  # noqa: E402

pytestmark = pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="real ffmpeg binary not installed")


def test_solid_color_clip_is_flagged_as_flat(tmp_path: Path) -> None:
    """A real, solid-color video (stddev exactly 0.0 per channel) is the
    negative control matching the known garbage-frame failure mode."""
    clip_path = make_color_clip(tmp_path / "flat.mp4", color="gray", duration=1.0, size="64x64", rate=8)

    result = analyze_video(Path(clip_path), num_samples=3)

    assert result["flat_frame_suspected"] is True
    assert result["avg_stddev"] < FLAT_FRAME_STDDEV_THRESHOLD
    # A seek right at the very end of a short clip can return an empty
    # frame (skipped, not a crash - see analyze_video's docstring); at
    # least 2 of the 3 requested samples must still come back real.
    assert result["num_frames_sampled"] >= 2
    for frame in result["per_frame_stats"]:
        assert frame["stddev_r"] == 0.0
        assert frame["stddev_g"] == 0.0
        assert frame["stddev_b"] == 0.0
    # A perfectly flat, unmoving, colorless clip is also the real
    # negative control for the newer sharpness/saturation/frame-delta
    # metrics - all must read exactly zero, not just "low".
    assert result["avg_sharpness"] == 0.0
    assert result["avg_saturation"] == 0.0
    assert result["avg_frame_delta"] == 0.0
    assert all(delta == 0.0 for delta in result["frame_deltas"])


def test_varied_testsrc_clip_is_not_flagged_as_flat(tmp_path: Path) -> None:
    """ffmpeg's own `testsrc` lavfi source (color bars/gradient pattern)
    is real varied content - the positive control proving this tool
    doesn't flag everything, only genuinely flat/muddy output."""
    import subprocess

    clip_path = tmp_path / "varied.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc=size=64x64:duration=1:rate=8",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(clip_path),
        ],
        check=True,
    )

    result = analyze_video(clip_path, num_samples=3)

    assert result["flat_frame_suspected"] is False
    assert result["avg_stddev"] >= FLAT_FRAME_STDDEV_THRESHOLD
    # Positive control for the newer metrics: a real, detailed, moving
    # pattern must score meaningfully above zero on all three, unlike
    # the flat clip's exact-zero negative control above.
    assert result["avg_sharpness"] > 0.0
    assert result["avg_saturation"] > 0.0
    assert result["avg_frame_delta"] > 0.0
    assert result["width"] == 64
    assert result["height"] == 64


def test_analyze_video_rejects_a_nonexistent_path(tmp_path: Path) -> None:
    with pytest.raises(Exception):  # noqa: B017 - real ffprobe/ffmpeg raises subprocess.CalledProcessError
        analyze_video(tmp_path / "does-not-exist.mp4")
