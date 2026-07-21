"""AssetPackager (services/export-service): bundles a final export +
thumbnails + subtitles into a schema-valid RenderManifest. Real ffmpeg
export + real SRT/VTT files on disk, real schema validation."""

from __future__ import annotations

import os

import pytest
import schemas
from asset_manager import AssetManager
from export_service import AssetPackager, ExportService
from media_helpers import FFMPEG_AVAILABLE, make_color_clip
from post_processing import SubtitleGenerator, ThumbnailEngine

pytestmark = pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg not installed - see docs/DEV_SETUP.md")


@pytest.fixture
def _export_result(tmp_path):
    clip = make_color_clip(tmp_path / "master.mp4", "teal", duration=2.0)
    asset_manager = AssetManager()
    service = ExportService(asset_manager, output_dir=tmp_path / "exports")
    return asset_manager, service.export("proj_pkg", clip, {"format": "mp4", "quality_preset": "720p"})


def test_package_with_only_a_video_is_schema_valid(_export_result):
    _, export_result = _export_result
    manifest = AssetPackager().package("proj_pkg", export_result)
    schemas.validate(manifest, "render_manifest")
    assert manifest["video"]["asset_id"] == export_result["asset_id"]
    assert manifest["thumbnails"] == []
    assert manifest["subtitles"] == []


def test_package_includes_thumbnails(tmp_path, _export_result):
    asset_manager, export_result = _export_result
    thumb_engine = ThumbnailEngine(asset_manager, output_dir=tmp_path / "thumbs")
    clip = make_color_clip(tmp_path / "for_thumb.mp4", "teal", duration=2.0)
    thumb_asset = thumb_engine.auto_thumbnail("proj_pkg", clip, duration_sec=2.0)

    manifest = AssetPackager(output_dir=tmp_path / "manifests").package(
        "proj_pkg",
        export_result,
        thumbnails=[
            {
                "asset_id": thumb_asset["asset_id"],
                "uri": thumb_asset["versions"][-1]["uri"],
                "kind": "auto",
                "timestamp_sec": 1.0,
            }
        ],
    )
    schemas.validate(manifest, "render_manifest")
    assert len(manifest["thumbnails"]) == 1


def test_package_writes_real_srt_and_vtt_files_for_non_burned_in_subtitles(tmp_path, _export_result):
    _, export_result = _export_result
    sub_track = SubtitleGenerator().generate_from_cues(
        "proj_pkg", "en", [{"start_sec": 0, "end_sec": 2, "text": "Hello"}]
    )

    manifest = AssetPackager(output_dir=tmp_path / "manifests").package(
        "proj_pkg", export_result, subtitle_tracks=[sub_track]
    )
    schemas.validate(manifest, "render_manifest")

    formats = {entry["format"] for entry in manifest["subtitles"]}
    assert formats == {"srt", "vtt"}
    for entry in manifest["subtitles"]:
        path = entry["uri"].replace("file://", "")
        assert os.path.exists(path)
        assert os.path.getsize(path) > 0
        assert entry["burned_in"] is False


def test_package_records_burned_in_subtitles_without_a_separate_file(tmp_path, _export_result):
    _, export_result = _export_result
    sub_track = SubtitleGenerator().generate_from_cues(
        "proj_pkg", "en", [{"start_sec": 0, "end_sec": 2, "text": "Hello"}], burned_in=True
    )

    manifest = AssetPackager(output_dir=tmp_path / "manifests").package(
        "proj_pkg", export_result, subtitle_tracks=[sub_track]
    )
    schemas.validate(manifest, "render_manifest")

    assert len(manifest["subtitles"]) == 1
    assert manifest["subtitles"][0]["burned_in"] is True
    assert manifest["subtitles"][0]["uri"] == export_result["uri"]


def test_package_includes_arbitrary_metadata(_export_result):
    _, export_result = _export_result
    manifest = AssetPackager().package("proj_pkg", export_result, metadata={"logline": "a test film"})
    assert manifest["metadata"]["logline"] == "a test film"
