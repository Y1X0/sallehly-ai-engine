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

eval/reports/0022 flagged that this tool measured per-frame stats only,
with no real frame-to-frame (temporal) metric - motion/flicker
stability could only be inferred indirectly from the denoising
trajectory in the pipeline's own diagnostics, not measured from the
decoded video itself. Three metrics were added directly to close that
gap, all pure stdlib (no PIL/numpy/OpenCV, same as the rest of this
file): `sharpness` (mean luma gradient magnitude - a blur/detail
proxy), `saturation` (mean per-pixel HSV-style saturation - a
color-vividness proxy), and `frame_deltas`/`avg_frame_delta` (mean
absolute byte difference between consecutive sampled frames - a real,
direct temporal-stability/flicker proxy: near-zero suggests a frozen/
static generation, a moderate value suggests coherent motion, a wildly
erratic one suggests flicker/instability).

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


def _probe_dimensions(video_path: Path) -> tuple[int, int]:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=p=0:s=x",
            str(video_path),
        ],
        check=True, capture_output=True, text=True,
    )
    width_str, height_str = result.stdout.strip().split("x")
    return int(width_str), int(height_str)


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


def _frame_sharpness(raw_rgb: bytes, width: int, height: int) -> float:
    """Mean absolute horizontal+vertical pixel gradient of luma - a real,
    cheap sharpness proxy (no PIL/numpy/OpenCV): a blurry/flat frame has
    small gradients between neighboring pixels; a sharp, detailed frame
    has large ones. Computed on luma (0.299R+0.587G+0.114B) to avoid
    conflating this with the existing per-channel color stats."""
    luma = bytearray(width * height)
    for i in range(width * height):
        r, g, b = raw_rgb[3 * i], raw_rgb[3 * i + 1], raw_rgb[3 * i + 2]
        luma[i] = int(0.299 * r + 0.587 * g + 0.114 * b)

    total = 0
    count = 0
    for y in range(height):
        row = y * width
        for x in range(width - 1):
            total += abs(luma[row + x + 1] - luma[row + x])
            count += 1
    for y in range(height - 1):
        row = y * width
        next_row = (y + 1) * width
        for x in range(width):
            total += abs(luma[next_row + x] - luma[row + x])
            count += 1
    return round(total / count, 3) if count else 0.0


def _frame_saturation(raw_rgb: bytes) -> float:
    """Mean HSV-style saturation ((max-min)/max per pixel, 0 for a
    black pixel) - a real per-pixel color-vividness proxy computed
    directly from the same raw RGB bytes, no colorspace-conversion
    library needed."""
    total = 0.0
    num_pixels = len(raw_rgb) // 3
    for i in range(num_pixels):
        r, g, b = raw_rgb[3 * i], raw_rgb[3 * i + 1], raw_rgb[3 * i + 2]
        hi = max(r, g, b)
        lo = min(r, g, b)
        total += (hi - lo) / hi if hi else 0.0
    return round(total / num_pixels, 4) if num_pixels else 0.0


def _frame_delta(raw_a: bytes, raw_b: bytes) -> float:
    """Mean absolute per-byte difference between two same-sized raw RGB
    frames - a real, direct temporal-stability/flicker proxy: two
    consecutive real frames of coherent motion differ by a moderate
    amount; a flickering or unstable generation swings wildly between
    samples; a frozen/static generation is near-zero. Requires both
    frames to be the same size (same resolution) - the caller's
    responsibility, since every sample in one analyze_video() call
    comes from the same video."""
    if len(raw_a) != len(raw_b):
        raise ValueError(f"frame size mismatch: {len(raw_a)} vs {len(raw_b)} bytes - not the same video/resolution")
    total = sum(abs(a - b) for a, b in zip(raw_a, raw_b))
    return round(total / len(raw_a), 3)


def analyze_video(video_path: Path, *, num_samples: int = 5) -> dict:
    """Samples `num_samples` real frames spread across the video's real
    duration and returns per-frame RGB stats plus overall
    `flat_frame_suspected`, sharpness, saturation, and (for 2+ real
    samples) frame-to-frame delta verdicts. Raises `ValueError` if
    `video_path` isn't a real, readable video - never returns a
    placeholder result."""
    duration = _probe_duration_sec(video_path)
    if duration <= 0:
        raise ValueError(f"{video_path}: ffprobe reported duration={duration!r} - not a real video")
    width, height = _probe_dimensions(video_path)

    if num_samples > 1:
        # 0.98 keeps the last sample safely before EOF - seeking exactly
        # at/after the real duration can return an empty frame.
        timestamps = [duration * i / (num_samples - 1) * 0.98 for i in range(num_samples)]
    else:
        timestamps = [duration / 2]

    per_frame = []
    raw_frames = []
    for ts in timestamps:
        raw = _extract_rgb_frame(video_path, ts)
        if not raw:
            continue
        per_frame.append({
            "timestamp_sec": round(ts, 3),
            **_frame_channel_stats(raw),
            "sharpness": _frame_sharpness(raw, width, height),
            "saturation": _frame_saturation(raw),
        })
        raw_frames.append(raw)

    if not per_frame:
        raise ValueError(f"{video_path}: ffmpeg could not extract any real frames")

    avg_stddev = statistics.fmean(
        statistics.fmean([f["stddev_r"], f["stddev_g"], f["stddev_b"]]) for f in per_frame
    )
    avg_sharpness = statistics.fmean(f["sharpness"] for f in per_frame)
    avg_saturation = statistics.fmean(f["saturation"] for f in per_frame)

    # Frame-to-frame delta (temporal stability/flicker proxy): only
    # meaningful with 2+ real samples of the same resolution, which
    # every real video here always is (raw_frames all come from the
    # same _probe_dimensions call) - a real, direct measurement, not an
    # inference from the denoising trajectory alone.
    frame_deltas = [_frame_delta(raw_frames[i], raw_frames[i + 1]) for i in range(len(raw_frames) - 1)]
    avg_frame_delta = round(statistics.fmean(frame_deltas), 3) if frame_deltas else None

    return {
        "video_path": str(video_path),
        "duration_sec": round(duration, 3),
        "width": width,
        "height": height,
        "num_frames_sampled": len(per_frame),
        "per_frame_stats": per_frame,
        "avg_stddev": round(avg_stddev, 2),
        "flat_frame_suspected": avg_stddev < FLAT_FRAME_STDDEV_THRESHOLD,
        "flat_frame_stddev_threshold": FLAT_FRAME_STDDEV_THRESHOLD,
        "avg_sharpness": round(avg_sharpness, 3),
        "avg_saturation": round(avg_saturation, 4),
        "frame_deltas": frame_deltas,
        "avg_frame_delta": avg_frame_delta,
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
