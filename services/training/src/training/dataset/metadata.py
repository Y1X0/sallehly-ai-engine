from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_HASH_CHUNK_BYTES = 1024 * 1024


class FfprobeNotAvailableError(Exception):
    """Raised when `ffprobe` isn't on PATH. Deliberately a self-contained
    check rather than importing `services/post-processing`'s own
    `ffmpeg_utils.probe()` - that package pulls in `video-composition-sdk`/
    `asset-manager`, a heavier and domain-mismatched dependency for a
    package that only ever reads *raw source footage* metadata, never
    produces or composites video. Same external-tool-dependency shape as
    that module (see docs/DEV_SETUP.md), just not the same code path."""


@dataclass(frozen=True)
class ClipMetadata:
    """Real, ffprobe-derived facts about one raw video file - no model,
    no GPU, just `ffprobe -show_format -show_streams`. This is the input
    `DatasetValidator`/`DatasetManager` reason about; nothing here is
    guessed or hardcoded."""

    duration_sec: float
    width: int
    height: int
    fps: float
    codec: str
    size_bytes: int
    file_hash: str

    @property
    def resolution(self) -> str:
        return f"{self.width}x{self.height}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "duration_sec": self.duration_sec,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "codec": self.codec,
            "size_bytes": self.size_bytes,
            "file_hash": self.file_hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ClipMetadata":
        return cls(
            duration_sec=data["duration_sec"],
            width=data["width"],
            height=data["height"],
            fps=data["fps"],
            codec=data["codec"],
            size_bytes=data["size_bytes"],
            file_hash=data["file_hash"],
        )


def _local_path(uri: str) -> str:
    parsed = urlparse(uri)
    return parsed.path if parsed.scheme == "file" else uri


def _ffprobe_path() -> str:
    path = shutil.which("ffprobe")
    if path is None:
        raise FfprobeNotAvailableError("ffprobe is not installed or not on PATH - see docs/DEV_SETUP.md")
    return path


def _parse_fps(rate: str) -> float:
    # ffprobe reports frame rate as a rational "num/den" string
    # (e.g. "30000/1001" for 29.97fps) rather than a decimal.
    if "/" in rate:
        num, _, den = rate.partition("/")
        den_f = float(den)
        return round(float(num) / den_f, 3) if den_f else 0.0
    return float(rate)


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(_HASH_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def extract_clip_metadata(source_uri: str) -> ClipMetadata:
    """Runs a real `ffprobe` subprocess against `source_uri` (a local
    path or `file://` URI) and a real SHA-256 file hash - both fully
    real, CPU-only operations requiring nothing beyond `ffprobe` on
    PATH. `file_hash` is what `HashDuplicateDetector` (duplicates.py)
    keys on for exact-duplicate detection."""
    path = Path(_local_path(source_uri))
    if not path.is_file():
        raise FileNotFoundError(f"No such clip file: {source_uri}")

    cmd = [_ffprobe_path(), "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed (exit {result.returncode}): {result.stderr.strip()}")
    probed = json.loads(result.stdout)

    video_stream = next((s for s in probed["streams"] if s.get("codec_type") == "video"), None)
    if video_stream is None:
        raise ValueError(f"No video stream found in {source_uri}")

    duration_sec = float(probed["format"].get("duration") or video_stream.get("duration") or 0.0)
    return ClipMetadata(
        duration_sec=round(duration_sec, 3),
        width=int(video_stream["width"]),
        height=int(video_stream["height"]),
        fps=_parse_fps(video_stream.get("r_frame_rate", "0/1")),
        codec=str(video_stream.get("codec_name", "unknown")),
        size_bytes=int(probed["format"].get("size") or path.stat().st_size),
        file_hash=_file_hash(path),
    )
