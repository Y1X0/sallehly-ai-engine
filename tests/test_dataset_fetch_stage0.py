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


class TestSlugForUrl:
    """Regression test: naming downloaded files by list position
    ("<category>_00", "_01", ...) meant a fresh run (e.g. retrying just
    the URLs that failed) restarted at index 0 and silently overwrote a
    previous run's already-downloaded clip - a real clip was lost this
    way during live testing. The slug must be derived from the URL
    itself so re-running never collides with a different source's file.
    """

    def test_derives_a_stable_slug_from_a_commons_title(self):
        module = _load_module()
        slug = module.slug_for_url("https://commons.wikimedia.org/wiki/File:Some_Video.webm")
        assert slug == "Some_Video"

    def test_is_stable_across_repeated_calls_for_the_same_url(self):
        module = _load_module()
        url = "https://commons.wikimedia.org/wiki/File:Repeat_Me.webm"
        assert module.slug_for_url(url) == module.slug_for_url(url)

    def test_different_commons_titles_do_not_collide(self):
        module = _load_module()
        a = module.slug_for_url("https://commons.wikimedia.org/wiki/File:Video_A.webm")
        b = module.slug_for_url("https://commons.wikimedia.org/wiki/File:Video_B.webm")
        assert a != b

    def test_falls_back_to_the_url_path_stem_for_a_direct_url(self):
        module = _load_module()
        slug = module.slug_for_url("https://images-assets.nasa.gov/video/PIA12345/PIA12345~orig.mp4")
        assert "PIA12345" in slug

    def test_sanitizes_unsafe_filesystem_characters(self):
        module = _load_module()
        slug = module.slug_for_url("https://commons.wikimedia.org/wiki/File:Weird%20%26%20Name%3F.webm")
        assert all(c.isalnum() or c in "._-" for c in slug)


class TestResolveAndDownloadRateLimitRetry:
    """Regression test: 4 of 9 real Wikimedia Commons downloads failed in
    live Kaggle testing with HTTP 429 Too many requests after several
    back-to-back fetches with no delay. resolve_and_download must back off
    and retry on 429, but must not retry (or sleep needlessly) on other
    errors, and must not retry forever.
    """

    def test_retries_and_succeeds_after_a_429(self, tmp_path):
        module = _load_module()
        call_count = {"n": 0}

        def fake_resolve(url):
            return "https://example.com/clip.mp4"

        def fake_download(url, dest_without_ext):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise module.urllib.error.HTTPError(url, 429, "Too many requests", {}, None)
            return dest_without_ext.with_suffix(".mp4")

        with patch.object(module, "resolve", fake_resolve), patch.object(module, "download", fake_download), patch.object(module.time, "sleep"):
            result = module.resolve_and_download("https://commons.wikimedia.org/wiki/File:X.webm", tmp_path / "x")

        assert call_count["n"] == 2  # failed once, succeeded on retry
        assert result == (tmp_path / "x").with_suffix(".mp4")

    def test_gives_up_after_max_retries_on_persistent_429(self):
        module = _load_module()

        def fake_download(url, dest_without_ext):
            raise module.urllib.error.HTTPError(url, 429, "Too many requests", {}, None)

        with patch.object(module, "resolve", lambda url: url), patch.object(module, "download", fake_download), patch.object(module.time, "sleep"):
            with pytest.raises(module.urllib.error.HTTPError):
                module.resolve_and_download("https://example.com/clip.mp4", Path("/tmp/x"))

    def test_does_not_retry_a_non_429_http_error(self):
        module = _load_module()
        call_count = {"n": 0}

        def fake_download(url, dest_without_ext):
            call_count["n"] += 1
            raise module.urllib.error.HTTPError(url, 404, "Not Found", {}, None)

        with patch.object(module, "resolve", lambda url: url), patch.object(module, "download", fake_download), patch.object(module.time, "sleep"):
            with pytest.raises(module.urllib.error.HTTPError):
                module.resolve_and_download("https://example.com/clip.mp4", Path("/tmp/x"))

        assert call_count["n"] == 1  # no retry for a 404 - only 429 is retried


class TestRunningUnderNotebookKernel:
    """Regression test: running this script's `if __name__ == "__main__"`
    block inside a real Kaggle/Colab notebook cell used to crash with
    "unrecognized arguments: -f .../kernel-xxx.json" because argparse
    fell back to parsing sys.argv, which under a notebook kernel holds the
    kernel launcher's own flags, not empty. `main` must be called with an
    explicit `[]` in that case instead of `None`.
    """

    def test_true_when_ipykernel_module_is_loaded(self):
        module = _load_module()
        with patch.object(module.sys, "modules", {**module.sys.modules, "ipykernel": object()}):
            assert module._running_under_notebook_kernel() is True

    def test_true_for_colab_kernel_launcher_argv0(self):
        module = _load_module()
        modules_without_ipykernel = {k: v for k, v in module.sys.modules.items() if k != "ipykernel"}
        with patch.object(module.sys, "modules", modules_without_ipykernel):
            with patch.object(module.sys, "argv", ["/usr/local/bin/colab_kernel_launcher.py", "-f", "kernel.json"]):
                assert module._running_under_notebook_kernel() is True

    def test_false_for_a_plain_script_invocation(self):
        module = _load_module()
        modules_without_ipykernel = {k: v for k, v in module.sys.modules.items() if k != "ipykernel"}
        with patch.object(module.sys, "modules", modules_without_ipykernel):
            with patch.object(module.sys, "argv", ["fetch_stage0.py", "--urls", "urls.json"]):
                assert module._running_under_notebook_kernel() is False


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
