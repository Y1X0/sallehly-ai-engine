"""Shared helpers for Phase 6 post-production tests: real synthetic
media generation via ffmpeg (lavfi test sources), so
TimelineBuilder/FfmpegCompositor/ThumbnailEngine/ExportService/etc. are
exercised against real files rather than mocks. See
docs/adr/0012-post-production-pipeline.md for why this pipeline is
tested with real ffmpeg execution instead of the mocked-boundary
approach used for GPU inference (ADR 0010) - ffmpeg is a real,
installable, executable dependency in a way a GPU or a live Temporal
server is not.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None


def make_color_clip(
    path: str | Path, color: str, duration: float, size: str = "320x240", rate: int = 24
) -> str:
    """A solid-color video clip with no audio - fast, deterministic,
    easy to assert on (sampling a pixel gives an exact expected color)."""
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:size={size}:duration={duration}:rate={rate}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
    )
    return str(path)


def make_tone(path: str | Path, duration: float, frequency: int = 440) -> str:
    """A sine-wave audio-only file."""
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency={frequency}:duration={duration}",
            "-c:a",
            "aac",
            str(path),
        ],
        check=True,
    )
    return str(path)


def make_image(path: str | Path, color: str, size: str = "64x64") -> str:
    """A single still image (e.g. a watermark logo)."""
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:size={size}:duration=0.1:rate=1",
            "-frames:v",
            "1",
            str(path),
        ],
        check=True,
    )
    return str(path)


def sample_pixel(video_path: str | Path, timestamp_sec: float, x: int = 0, y: int = 0) -> tuple[int, int, int]:
    """Returns the (r, g, b) of the pixel at (x, y) in the frame at
    `timestamp_sec` - lets tests assert on real rendered pixel values
    (e.g. "is this frame red, or has it faded to black"). Crops a 2x2
    region rather than 1x1 - this ffmpeg build's `crop` filter rejects a
    1-pixel size ("Invalid too big or non positive size"), confirmed
    empirically; 2x2 works and the first pixel is all we need."""
    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            str(timestamp_sec),
            "-i",
            str(video_path),
            "-vframes",
            "1",
            "-vf",
            f"crop=2:2:{x}:{y}",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-",
        ],
        check=True,
        capture_output=True,
    )
    data = result.stdout
    return (data[0], data[1], data[2])


def count_color_pixels(video_path: str | Path, timestamp_sec: float, predicate) -> tuple[int, int]:
    """Extracts the frame at `timestamp_sec` and returns
    (matching_pixel_count, total_pixel_count) where `predicate(r, g, b)`
    decides whether a pixel matches - used to confirm something (e.g.
    burned-in subtitle text, a watermark) actually appears somewhere in
    the frame without needing an image library."""
    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            str(timestamp_sec),
            "-i",
            str(video_path),
            "-vframes",
            "1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-",
        ],
        check=True,
        capture_output=True,
    )
    data = result.stdout
    pixels = [(data[i], data[i + 1], data[i + 2]) for i in range(0, len(data), 3)]
    matching = sum(1 for p in pixels if predicate(*p))
    return matching, len(pixels)
