"""Tests for dataset/sources/fetch_stage0.py's pure logic - URL
resolution (mocked network) and the ffprobe summary helper (real
ffmpeg-generated clip, same convention as
test_training_scripts_ingest_dataset.py). No real network access is
exercised - Wikimedia Commons/NASA responses are mocked with realistic
shapes taken from their documented API responses.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from media_helpers import FFMPEG_AVAILABLE, make_color_clip

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "dataset" / "sources" / "fetch_stage0.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("fetch_stage0_under_test", _SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def read(self) -> bytes:
        return self._payload


class TestResolveCommonsUrl:
    def test_resolves_a_real_shaped_commons_api_response(self):
        module = _load_module()
        fake_payload = json.dumps(
            {
                "query": {
                    "pages": {
                        "12345": {
                            "imageinfo": [
                                {"url": "https://upload.wikimedia.org/wikipedia/commons/1/1a/Group_dance.webm"}
                            ]
                        }
                    }
                }
            }
        ).encode()

        with patch.object(module.urllib.request, "urlopen", return_value=_FakeResponse(fake_payload)):
            result = module.resolve_commons_url("https://commons.wikimedia.org/wiki/File:Group_dance.webm")

        assert result == "https://upload.wikimedia.org/wikipedia/commons/1/1a/Group_dance.webm"

    def test_rejects_a_non_file_page_url(self):
        module = _load_module()
        with pytest.raises(ValueError, match="not a Commons File"):
            module.resolve_commons_url("https://commons.wikimedia.org/wiki/Category:Videos_of_sports")

    def test_raises_when_api_has_no_imageinfo(self):
        module = _load_module()
        fake_payload = json.dumps({"query": {"pages": {"-1": {"missing": ""}}}}).encode()

        with patch.object(module.urllib.request, "urlopen", return_value=_FakeResponse(fake_payload)):
            with pytest.raises(ValueError, match="no imageinfo"):
                module.resolve_commons_url("https://commons.wikimedia.org/wiki/File:Does_not_exist.webm")


class TestResolveNasaUrl:
    def test_resolves_a_real_shaped_nasa_asset_manifest(self):
        module = _load_module()
        fake_payload = json.dumps(
            {
                "collection": {
                    "items": [
                        {"href": "https://images-assets.nasa.gov/video/PIA12345/PIA12345~thumb.mp4"},
                        {"href": "https://images-assets.nasa.gov/video/PIA12345/PIA12345~orig.mp4"},
                    ]
                }
            }
        ).encode()

        with patch.object(module.urllib.request, "urlopen", return_value=_FakeResponse(fake_payload)):
            result = module.resolve_nasa_url("https://images.nasa.gov/details/PIA12345")

        assert result == "https://images-assets.nasa.gov/video/PIA12345/PIA12345~orig.mp4"

    def test_raises_when_no_mp4_asset_present(self):
        module = _load_module()
        fake_payload = json.dumps(
            {"collection": {"items": [{"href": "https://images-assets.nasa.gov/video/PIA1/PIA1.srt"}]}}
        ).encode()

        with patch.object(module.urllib.request, "urlopen", return_value=_FakeResponse(fake_payload)):
            with pytest.raises(ValueError, match="no .mp4 asset"):
                module.resolve_nasa_url("https://images.nasa.gov/details/PIA1")

    def test_rejects_a_url_with_no_recognizable_nasa_id(self):
        module = _load_module()
        with pytest.raises(ValueError, match="could not find a NASA asset id"):
            module.resolve_nasa_url("https://images.nasa.gov/")


class TestResolve:
    def test_passes_through_an_already_direct_url_unchanged(self):
        module = _load_module()
        direct = "https://example.com/some_clip.mp4"
        assert module.resolve(direct) == direct


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed")
class TestFfprobeSummary:
    def test_reports_real_dimensions_for_a_real_clip(self, tmp_path):
        module = _load_module()
        clip_path = tmp_path / "clip.mp4"
        make_color_clip(clip_path, "red", duration=1.0, size="640x480", rate=24)

        summary = module.ffprobe_summary(clip_path)

        assert "width=640" in summary
        assert "height=480" in summary

    def test_does_not_raise_for_a_nonexistent_file(self, tmp_path):
        module = _load_module()
        summary = module.ffprobe_summary(tmp_path / "does_not_exist.mp4")
        assert "ffprobe failed" in summary


class TestMainGuardsEmptyCategoryUrls:
    def test_refuses_when_category_urls_and_no_file_are_both_empty(self, capsys):
        module = _load_module()
        for urls in module.CATEGORY_URLS.values():
            assert urls == []  # the shipped template must stay empty - real URLs get pasted in, not committed

        exit_code = module.main([])

        assert exit_code == 1
        assert "CATEGORY_URLS is empty" in capsys.readouterr().out
