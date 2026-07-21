"""WatermarkEngine (services/post-processing) + FfmpegCompositor's
watermark overlay: real ffmpeg execution, verified by sampling actual
rendered pixels."""

from __future__ import annotations

import pytest
from asset_manager import AssetManager
from media_helpers import FFMPEG_AVAILABLE, make_color_clip, make_image, sample_pixel
from post_processing import WatermarkEngine, WatermarkEngineError, register_defaults
from post_processing.compositor import FfmpegCompositor, timeline_from_dict

pytestmark = pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg not installed - see docs/DEV_SETUP.md")


@pytest.fixture(autouse=True)
def _register_builtins():
    register_defaults()


def _base_timeline(clip_uri: str, duration: float = 2.0) -> dict:
    return {
        "schema_version": "1.0",
        "project_id": "proj_wm",
        "fps": 24,
        "resolution": "320x240",
        "video_clips": [{"clip_id": "c1", "shot_id": "s1", "source_uri": clip_uri, "duration_sec": duration}],
    }


def test_with_logo_overlay_attaches_watermark_to_timeline(tmp_path):
    logo = make_image(tmp_path / "logo.png", "white", size="64x64")
    asset_manager = AssetManager()
    logo_asset = asset_manager.register(project_id="proj_wm", kind="image", uri=logo)

    engine = WatermarkEngine(asset_manager)
    timeline = engine.with_logo_overlay(
        _base_timeline("file:///irrelevant.mp4"), logo_asset["asset_id"], position="top_left", opacity=1.0, scale=0.2
    )
    assert timeline["watermark"]["logo_asset_id"] == logo_asset["asset_id"]
    assert timeline["watermark"]["logo_position"] == "top_left"


def test_with_logo_overlay_rejects_unknown_asset():
    asset_manager = AssetManager()
    engine = WatermarkEngine(asset_manager)
    with pytest.raises(WatermarkEngineError, match="No such asset"):
        engine.with_logo_overlay(_base_timeline("x"), "asset_does_not_exist")


def test_compositor_renders_a_visible_watermark_overlay(tmp_path):
    clip = make_color_clip(tmp_path / "clip.mp4", "green", duration=2.0)
    logo = make_image(tmp_path / "logo.png", "white", size="80x60")

    asset_manager = AssetManager()
    logo_asset = asset_manager.register(project_id="proj_wm", kind="image", uri=logo)

    engine = WatermarkEngine(asset_manager)
    timeline_dict = engine.with_logo_overlay(
        _base_timeline(clip), logo_asset["asset_id"], position="top_left", opacity=1.0, scale=0.5
    )

    output_path = tmp_path / "out.mp4"
    FfmpegCompositor(asset_manager=asset_manager).compose(timeline_from_dict(timeline_dict), output_path)

    # top-left corner should now be the white logo, not the green background.
    # (overlay is inset 10px per _apply_watermark's position map, and the logo
    # is scaled to 50% of the 320px frame width = 160px wide, so (30,30) is
    # comfortably inside it.)
    top_left = sample_pixel(output_path, 1.0, x=30, y=30)
    assert top_left[0] > 200 and top_left[1] > 200 and top_left[2] > 200

    # bottom-right corner is untouched - still the green background
    # (X11 "green" is (0,128,0), not pure (0,255,0), and h264 compression
    # softens it further - compare G to R/B rather than an absolute threshold).
    bottom_right = sample_pixel(output_path, 1.0, x=300, y=220)
    assert bottom_right[1] > bottom_right[0] + 30 and bottom_right[1] > bottom_right[2] + 30


def test_with_intro_prepends_a_real_clip_and_extends_duration(tmp_path):
    main_clip = make_color_clip(tmp_path / "main.mp4", "blue", duration=2.0)
    intro_clip = make_color_clip(tmp_path / "intro.mp4", "white", duration=1.0)

    asset_manager = AssetManager()
    intro_asset = asset_manager.register(project_id="proj_wm", kind="video", uri=intro_clip)

    engine = WatermarkEngine(asset_manager)
    timeline_dict = _base_timeline(main_clip, duration=2.0)
    timeline_dict["total_duration_sec"] = 2.0
    timeline_dict = engine.with_intro(timeline_dict, intro_asset["asset_id"], duration_sec=1.0)

    assert len(timeline_dict["video_clips"]) == 2
    assert timeline_dict["video_clips"][0]["shot_id"] == "branding_intro"
    assert timeline_dict["total_duration_sec"] == 3.0

    output_path = tmp_path / "out.mp4"
    FfmpegCompositor(asset_manager=asset_manager).compose(timeline_from_dict(timeline_dict), output_path)

    # first second is the white intro, the rest is the blue main clip.
    assert sample_pixel(output_path, 0.3)[0] > 200  # white-ish
    assert sample_pixel(output_path, 2.0)[2] > 200  # blue
