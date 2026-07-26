"""Tests for services/training/src/training/hf_download.py - real
download-manifest bookkeeping and checksum verification, with a fake
`download_fn` injected in place of `huggingface_hub.snapshot_download`
(same injectable-callable pattern `KaggleClient`/`ModalJobLauncher`
already use for `subprocess.run`). No network access or real Hugging
Face download happens in this file.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from training import (
    HFDownloadError,
    HuggingFaceWeightsDownloader,
    load_wan22_registry_entries,
    resolve_local_weights,
)

_REGISTRY_PATH = Path(__file__).resolve().parents[1] / "models" / "registry.yaml"


def _fake_download_fn(files: dict[str, bytes]):
    def _download(**kwargs) -> str:
        local_dir = Path(kwargs["local_dir"])
        for relative_path, content in files.items():
            path = local_dir / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        return str(local_dir)

    return _download


@pytest.fixture()
def wan22_entry():
    entries = load_wan22_registry_entries(_REGISTRY_PATH)
    return entries["wan2.2-ti2v-5b"]


class TestHuggingFaceWeightsDownloader:
    def test_download_writes_files_and_records_checksums(self, tmp_path, wan22_entry):
        downloader = HuggingFaceWeightsDownloader(
            cache_root=tmp_path / "cache",
            download_fn=_fake_download_fn({"transformer/config.json": b"{}", "model_index.json": b"{}"}),
        )

        manifest = downloader.download(wan22_entry)

        assert manifest.engine_id == "wan2.2-ti2v-5b"
        assert manifest.repo_id == wan22_entry.download.repo_id
        assert set(manifest.files) == {"transformer/config.json", "model_index.json"}
        assert (Path(manifest.local_dir) / "transformer" / "config.json").exists()

    def test_download_raises_when_no_files_produced(self, tmp_path, wan22_entry):
        downloader = HuggingFaceWeightsDownloader(cache_root=tmp_path / "cache", download_fn=_fake_download_fn({}))

        with pytest.raises(HFDownloadError, match="produced no files"):
            downloader.download(wan22_entry)

    def test_second_download_short_circuits_via_cached_manifest(self, tmp_path, wan22_entry):
        calls = {"count": 0}

        def counting_download(**kwargs) -> str:
            calls["count"] += 1
            local_dir = Path(kwargs["local_dir"])
            (local_dir / "model_index.json").write_text("{}")
            return str(local_dir)

        downloader = HuggingFaceWeightsDownloader(cache_root=tmp_path / "cache", download_fn=counting_download)

        first = downloader.download(wan22_entry)
        second = downloader.download(wan22_entry)

        assert calls["count"] == 1
        assert first.local_dir == second.local_dir

    def test_force_redownloads_even_with_cached_manifest(self, tmp_path, wan22_entry):
        calls = {"count": 0}

        def counting_download(**kwargs) -> str:
            calls["count"] += 1
            local_dir = Path(kwargs["local_dir"])
            (local_dir / "model_index.json").write_text("{}")
            return str(local_dir)

        downloader = HuggingFaceWeightsDownloader(cache_root=tmp_path / "cache", download_fn=counting_download)
        downloader.download(wan22_entry)
        downloader.download(wan22_entry, force=True)

        assert calls["count"] == 2

    def test_resolve_local_weights_returns_none_when_nothing_downloaded(self, tmp_path):
        assert resolve_local_weights("wan2.2-ti2v-5b", cache_root=tmp_path / "cache") is None

    def test_resolve_local_weights_returns_manifest_after_download(self, tmp_path, wan22_entry):
        downloader = HuggingFaceWeightsDownloader(
            cache_root=tmp_path / "cache", download_fn=_fake_download_fn({"model_index.json": b"{}"}),
        )
        downloader.download(wan22_entry)

        resolved = resolve_local_weights("wan2.2-ti2v-5b", cache_root=tmp_path / "cache")

        assert resolved is not None
        assert resolved.engine_id == "wan2.2-ti2v-5b"
        resolved.verify()  # must not raise

    def test_verify_raises_on_missing_file(self, tmp_path, wan22_entry):
        downloader = HuggingFaceWeightsDownloader(
            cache_root=tmp_path / "cache", download_fn=_fake_download_fn({"model_index.json": b"{}"}),
        )
        manifest = downloader.download(wan22_entry)
        (Path(manifest.local_dir) / "model_index.json").unlink()

        with pytest.raises(HFDownloadError, match="missing"):
            manifest.verify()

    def test_verify_raises_on_checksum_mismatch(self, tmp_path, wan22_entry):
        downloader = HuggingFaceWeightsDownloader(
            cache_root=tmp_path / "cache", download_fn=_fake_download_fn({"model_index.json": b"original"}),
        )
        manifest = downloader.download(wan22_entry)
        (Path(manifest.local_dir) / "model_index.json").write_bytes(b"corrupted")

        with pytest.raises(HFDownloadError, match="checksum mismatch"):
            manifest.verify()
