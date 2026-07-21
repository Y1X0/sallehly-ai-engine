from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse


class FfmpegNotAvailableError(Exception):
    """Raised when the `ffmpeg`/`ffprobe` binary isn't on PATH. Both are
    an external system dependency the way RunPod/Temporal deployments
    are - see docs/DEV_SETUP.md for install instructions. Every real
    filesystem/media operation in services/post-processing and
    services/export-service goes through this module so that dependency
    is checked in exactly one place."""


class FfmpegCommandError(Exception):
    """An ffmpeg/ffprobe invocation exited non-zero - message includes
    stderr and the full command for debugging."""


def ffmpeg_path() -> str:
    path = shutil.which("ffmpeg")
    if path is None:
        raise FfmpegNotAvailableError("ffmpeg is not installed or not on PATH - see docs/DEV_SETUP.md")
    return path


def ffprobe_path() -> str:
    path = shutil.which("ffprobe")
    if path is None:
        raise FfmpegNotAvailableError("ffprobe is not installed or not on PATH - see docs/DEV_SETUP.md")
    return path


def run_ffmpeg(args: list[str], *, overwrite: bool = True) -> subprocess.CompletedProcess[str]:
    """Runs `ffmpeg -y|-n -hide_banner -loglevel error <args>`, raising
    FfmpegCommandError with stderr on a non-zero exit."""
    cmd = [ffmpeg_path(), "-y" if overwrite else "-n", "-hide_banner", "-loglevel", "error", *args]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise FfmpegCommandError(
            f"ffmpeg failed (exit {result.returncode}): {result.stderr.strip()}\ncommand: {' '.join(cmd)}"
        )
    return result


def probe(path: str | Path) -> dict:
    """Runs `ffprobe -show_format -show_streams -of json` and returns
    the parsed result - duration_sec/resolution/fps/codec verification
    for anything this pipeline produces."""
    cmd = [ffprobe_path(), "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise FfmpegCommandError(f"ffprobe failed (exit {result.returncode}): {result.stderr.strip()}")
    return json.loads(result.stdout)


def local_path(uri: str) -> str:
    """Strips a file:// scheme, if present, to get a plain filesystem
    path. ffmpeg itself accepts file:// URIs directly (it has a `file`
    protocol handler) so this is only needed when *this* code - not
    ffmpeg - needs to touch the filesystem (e.g. checking existence)."""
    parsed = urlparse(uri)
    if parsed.scheme in ("", "file"):
        return parsed.path if parsed.scheme == "file" else uri
    return uri
