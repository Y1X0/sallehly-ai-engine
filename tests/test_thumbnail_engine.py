"""ThumbnailEngine (services/post-processing): real ffmpeg keyframe
extraction. Skipped if ffmpeg isn't installed."""

from __future__ import annotations

import os

import pytest
from asset_manager import AssetManager
from media_helpers import FFMPEG_AVAILABLE, make_color_clip
from post_processing import ThumbnailEngine

pytestmark = pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg not installed - see docs/DEV_SETUP.md")


def _uri_to_path(uri: str) -> str:
    return uri.replace("file://", "")


def test_scene_thumbnail_extracts_a_real_jpeg_file(tmp_path):
    clip = make_color_clip(tmp_path / "clip.mp4", "purple", duration=3.0)
    asset_manager = AssetManager()
    engine = ThumbnailEngine(asset_manager, output_dir=tmp_path / "thumbs")

    asset = engine.scene_thumbnail("proj_thumb", "shot_1", clip, duration_sec=3.0)

    assert asset["kind"] == "preview"
    assert asset["shot_id"] == "shot_1"
    path = _uri_to_path(asset["versions"][-1]["uri"])
    assert os.path.exists(path)
    assert os.path.getsize(path) > 0


def test_scene_thumbnail_uses_the_shot_midpoint(tmp_path):
    clip = make_color_clip(tmp_path / "clip.mp4", "purple", duration=4.0)
    asset_manager = AssetManager()
    engine = ThumbnailEngine(asset_manager, output_dir=tmp_path / "thumbs")

    asset = engine.scene_thumbnail("proj_thumb", "shot_1", clip, duration_sec=4.0)

    assert asset["versions"][-1]["metadata"]["timestamp_sec"] == 2.0


def test_auto_thumbnail_registers_a_project_level_asset_with_no_shot_id(tmp_path):
    clip = make_color_clip(tmp_path / "clip.mp4", "orange", duration=2.0)
    asset_manager = AssetManager()
    engine = ThumbnailEngine(asset_manager, output_dir=tmp_path / "thumbs")

    asset = engine.auto_thumbnail("proj_thumb2", clip, duration_sec=2.0)

    assert "shot_id" not in asset
    assert asset["kind"] == "preview"


def test_extract_keyframe_at_an_explicit_timestamp(tmp_path):
    clip = make_color_clip(tmp_path / "clip.mp4", "cyan", duration=4.0)
    asset_manager = AssetManager()
    engine = ThumbnailEngine(asset_manager, output_dir=tmp_path / "thumbs")

    asset = engine.extract_keyframe("proj_thumb3", clip, timestamp_sec=2.5, shot_id="shot_9")

    assert asset["versions"][-1]["metadata"]["timestamp_sec"] == 2.5
    path = _uri_to_path(asset["versions"][-1]["uri"])
    assert os.path.exists(path)


def test_multiple_thumbnails_for_the_same_shot_version_up(tmp_path):
    clip = make_color_clip(tmp_path / "clip.mp4", "pink", duration=3.0)
    asset_manager = AssetManager()
    engine = ThumbnailEngine(asset_manager, output_dir=tmp_path / "thumbs")

    first = engine.extract_keyframe("proj_thumb4", clip, timestamp_sec=0.5, shot_id="shot_1")
    second = engine.extract_keyframe("proj_thumb4", clip, timestamp_sec=2.5, shot_id="shot_1")

    assert first["asset_id"] == second["asset_id"]
    assert len(second["versions"]) == 2
