"""IUpscaler / PassthroughUpscaler (services/post-processing): the
prepared-but-not-implemented interface for video upscaling and frame
interpolation. No ffmpeg required - PassthroughUpscaler is a plain file
copy, by design (see its docstring for why)."""

from __future__ import annotations

import filecmp

from post_processing import PassthroughUpscaler
from video_composition_sdk import IUpscaler


def test_passthrough_upscaler_implements_iupscaler():
    assert isinstance(PassthroughUpscaler(), IUpscaler)


def test_upscale_copies_the_file_unchanged(tmp_path):
    source = tmp_path / "input.mp4"
    source.write_bytes(b"not-really-a-video-but-bytes-are-bytes")
    dest = tmp_path / "output.mp4"

    result = PassthroughUpscaler().upscale(source, dest, target_resolution="3840x2160")

    assert result == str(dest)
    assert filecmp.cmp(source, dest, shallow=False)


def test_interpolate_frames_copies_the_file_unchanged(tmp_path):
    source = tmp_path / "input.mp4"
    source.write_bytes(b"some-frame-data")
    dest = tmp_path / "output.mp4"

    PassthroughUpscaler().interpolate_frames(source, dest, target_fps=60)

    assert filecmp.cmp(source, dest, shallow=False)
