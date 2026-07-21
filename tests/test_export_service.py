"""ExportService (services/export-service): real ffmpeg re-encode for
every format/quality-preset combination."""

from __future__ import annotations

import pytest
from asset_manager import AssetManager
from export_service import ExportService
from export_service.quality_presets import QUALITY_PRESETS
from media_helpers import FFMPEG_AVAILABLE, make_tone
from post_processing.ffmpeg_utils import probe

pytestmark = pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg not installed - see docs/DEV_SETUP.md")


def _make_master(tmp_path) -> str:
    import subprocess

    clip = tmp_path / "master.mp4"
    tone = make_tone(tmp_path / "tone.aac", duration=2.0)
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
            "testsrc=duration=2:size=640x480:rate=24",
            "-i",
            tone,
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-pix_fmt",
            "yuv420p",
            str(clip),
        ],
        check=True,
    )
    return str(clip)


@pytest.mark.parametrize("preset", ["720p", "1080p", "1440p", "4k"])
def test_export_produces_the_correct_resolution_for_each_quality_preset(tmp_path, preset):
    master = _make_master(tmp_path)
    service = ExportService(AssetManager(), output_dir=tmp_path / "exports")

    result = service.export("proj_exp", master, {"format": "mp4", "quality_preset": preset})

    assert result["resolution"] == QUALITY_PRESETS[preset]["resolution"]


@pytest.mark.parametrize("fmt,expected_codec", [("mp4", "libx264"), ("mov", "libx264"), ("webm", "libvpx-vp9")])
def test_export_produces_the_correct_container_and_codec(tmp_path, fmt, expected_codec):
    master = _make_master(tmp_path)
    service = ExportService(AssetManager(), output_dir=tmp_path / "exports")

    result = service.export("proj_exp", master, {"format": fmt, "quality_preset": "720p"})

    assert result["format"] == fmt
    assert result["codec"] == expected_codec
    assert result["uri"].endswith(f".{fmt}")

    probed = probe(result["uri"].replace("file://", ""))
    video_stream = next(s for s in probed["streams"] if s["codec_type"] == "video")
    assert video_stream["codec_name"] in (expected_codec.replace("lib", ""), "vp9", "h264")


def test_export_registers_a_project_level_asset(tmp_path):
    master = _make_master(tmp_path)
    asset_manager = AssetManager()
    service = ExportService(asset_manager, output_dir=tmp_path / "exports")

    result = service.export("proj_exp", master, {"format": "mp4", "quality_preset": "720p"})

    asset = asset_manager.get(result["asset_id"])
    assert asset["kind"] == "video"
    assert "shot_id" not in asset


def test_export_rejects_unsupported_format(tmp_path):
    master = _make_master(tmp_path)
    service = ExportService(AssetManager(), output_dir=tmp_path / "exports")
    with pytest.raises(Exception):  # schema validation rejects it before ExportServiceError is even reached
        service.export("proj_exp", master, {"format": "avi", "quality_preset": "720p"})


def test_export_rejects_unsupported_quality_preset(tmp_path):
    master = _make_master(tmp_path)
    service = ExportService(AssetManager(), output_dir=tmp_path / "exports")
    with pytest.raises(Exception):
        service.export("proj_exp", master, {"format": "mp4", "quality_preset": "8k"})


def test_export_honors_explicit_bitrate_override(tmp_path):
    master = _make_master(tmp_path)
    service = ExportService(AssetManager(), output_dir=tmp_path / "exports")
    result = service.export(
        "proj_exp", master, {"format": "mp4", "quality_preset": "720p", "video_bitrate_kbps": 500}
    )
    assert result["resolution"] == "1280x720"
