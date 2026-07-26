"""Tests for services/training/scripts/download_wan22_weights.py - CLI
wiring around the real (but here, injected-fake) HuggingFaceWeightsDownloader.
No network access happens in this file.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "services" / "training" / "scripts" / "download_wan22_weights.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("download_wan22_weights_under_test", _SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestDownloadWan22Weights:
    def test_unknown_engine_id_fails(self, tmp_path, capsys):
        module = _load_module()

        exit_code = module.main(["--engine-id", "not-a-real-engine", "--cache-root", str(tmp_path / "cache")])

        assert exit_code == 1
        assert "No Wan2.2 registry entry" in capsys.readouterr().err

    def test_successful_download_with_injected_fake(self, tmp_path, monkeypatch):
        module = _load_module()

        def fake_download_fn(**kwargs) -> str:
            local_dir = Path(kwargs["local_dir"])
            (local_dir / "transformer").mkdir(parents=True, exist_ok=True)
            (local_dir / "transformer" / "config.json").write_text("{}")
            (local_dir / "model_index.json").write_text("{}")
            return str(local_dir)

        real_downloader_cls = module.HuggingFaceWeightsDownloader
        monkeypatch.setattr(
            module, "HuggingFaceWeightsDownloader",
            lambda **kwargs: real_downloader_cls(download_fn=fake_download_fn, **kwargs),
        )

        exit_code = module.main(["--engine-id", "wan2.2-ti2v-5b", "--cache-root", str(tmp_path / "cache")])

        assert exit_code == 0
        assert (tmp_path / "cache" / "wan2.2-ti2v-5b" / "download_manifest.json").is_file()
