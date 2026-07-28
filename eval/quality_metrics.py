#!/usr/bin/env python3
"""Real, reusable frame-quality inspection for Wan-generated videos.

Extracts real frames via `ffmpeg` (same real-subprocess convention as
`tests/media_helpers.py` - raw `rgb24` pipe, no PIL/numpy dependency)
and computes real per-channel pixel statistics with the standard
library's own `statistics` module.

This exists because two real Kaggle GPU runs (30303715804, 30316220351)
each produced a crash-free, correctly-sized `video.mp4` whose frames
silently decoded to near-flat, muddy, low-contrast noise instead of
real content - not caught by anything upstream, only found by manually
extracting frames and eyeballing pixel stats. This script turns that
by-hand check into a repeatable gate for every iteration of the
ongoing Kaggle-only quality-improvement loop (see eval/REPORT_TEMPLATE.md).

Usage:
    uv run python eval/quality_metrics.py path/to/video.mp4
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
from pathlib import Path

# Below this per-channel stddev, a frame is almost certainly the known
# flat/muddy failure mode rather than real rendered content - confirmed
# by hand against two real garbage runs (std ~10-14 across all three
# RGB channels) vs. this repo's own real-content test fixtures (a solid
# ffmpeg lavfi color clip, the actual negative control, has stddev
# exactly 0.0; any real photographic/rendered scene is essentially
# always well above 30).
FLAT_FRAME_STDDEV_THRESHOLD = 20.0


def _probe_duration_sec(video_path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "csv=p=0",
            str(video_path),
        ],
        check=True, capture_output=True, text=True,
    )
    return float(result.stdout.strip())


def _extract_rgb_frame(video_path: Path, timestamp_sec: float) -> bytes:
    result = subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-ss", str(timestamp_sec),
            "-i", str(video_path),
            "-vframes", "1",
            "-f", "rawvideo", "-pix_fmt", "rgb24",
            "-",
        ],
        check=True, capture_output=True,
    )
    return result.stdout


def _frame_channel_stats(raw_rgb: bytes) -> dict[str, float]:
    channels = {"r": raw_rgb[0::3], "g": raw_rgb[1::3], "b": raw_rgb[2::3]}
    stats: dict[str, float] = {}
    for name, values in channels.items():
        stats[f"mean_{name}"] = round(statistics.fmean(values), 2)
        stats[f"stddev_{name}"] = round(statistics.pstdev(values), 2) if len(values) > 1 else 0.0
        stats[f"min_{name}"] = min(values)
        stats[f"max_{name}"] = max(values)
    return stats


def analyze_video(video_path: Path, *, num_samples: int = 5) -> dict:
    """Samples `num_samples` real frames spread across the video's real
    duration and returns per-frame RGB stats plus an overall
    `flat_frame_suspected` verdict. Raises `ValueError` if `video_path`
    isn't a real, readable video - never returns a placeholder result."""
    duration = _probe_duration_sec(video_path)
    if duration <= 0:
        raise ValueError(f"{video_path}: ffprobe reported duration={duration!r} - not a real video")

    if num_samples > 1:
        # 0.98 keeps the last sample safely before EOF - seeking exactly
        # at/after the real duration can return an empty frame.
        timestamps = [duration * i / (num_samples - 1) * 0.98 for i in range(num_samples)]
    else:
        timestamps = [duration / 2]

    per_frame = []
    for ts in timestamps:
        raw = _extract_rgb_frame(video_path, ts)
        if not raw:
            continue
        per_frame.append({"timestamp_sec": round(ts, 3), **_frame_channel_stats(raw)})

    if not per_frame:
        raise ValueError(f"{video_path}: ffmpeg could not extract any real frames")

    avg_stddev = statistics.fmean(
        statistics.fmean([f["stddev_r"], f["stddev_g"], f["stddev_b"]]) for f in per_frame
    )
    return {
        "video_path": str(video_path),
        "duration_sec": round(duration, 3),
        "num_frames_sampled": len(per_frame),
        "per_frame_stats": per_frame,
        "avg_stddev": round(avg_stddev, 2),
        "flat_frame_suspected": avg_stddev < FLAT_FRAME_STDDEV_THRESHOLD,
        "flat_frame_stddev_threshold": FLAT_FRAME_STDDEV_THRESHOLD,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("video_path", type=Path)
    parser.add_argument("--num-samples", type=int, default=5)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = analyze_video(args.video_path, num_samples=args.num_samples)
    print(json.dumps(result, indent=2))
    if result["flat_frame_suspected"]:
        print(
            f"\nWARNING: avg per-frame stddev {result['avg_stddev']} is below "
            f"{FLAT_FRAME_STDDEV_THRESHOLD} - this looks like the known flat/muddy "
            "failure mode, not real rendered content.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
