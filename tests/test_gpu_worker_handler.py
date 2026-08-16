"""Tests for workers/gpu-worker/handler.py - the real RunPod serverless
handler for Wan2.2 inference (see its own module docstring). Covers the
handler's own orchestration (job dict parsing, weight-download caching,
storage upload wiring) with injected fakes for the real HF download and
real inference call - both of those are already covered for real
elsewhere (services/training's hf_download tests,
tests/test_video_engine_wan_inference.py) and would otherwise need real
network access / a real GPU.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

from training.hf_download import DownloadManifest

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "workers" / "gpu-worker" / "handler.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("gpu_worker_handler_under_test", _SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestEnsureWeightsDownloaded:
    def test_reuses_an_existing_verified_cache_without_downloading(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WAN22_MODELS_CACHE_ROOT", str(tmp_path / "cache"))
        module = _load_module()

        engine_dir = tmp_path / "cache" / module._ENGINE_ID
        engine_dir.mkdir(parents=True)
        weight_file = engine_dir / "model_index.json"
        weight_file.write_text("{}")
        manifest = DownloadManifest(
            engine_id=module._ENGINE_ID, repo_id="Wan-AI/Wan2.2-TI2V-5B-Diffusers", revision="main",
            local_dir=str(engine_dir), files={"model_index.json": hashlib.sha256(weight_file.read_bytes()).hexdigest()},
            downloaded_at="2026-01-01T00:00:00+00:00",
        )
        (engine_dir / "download_manifest.json").write_text(json.dumps(manifest.to_dict()))

        def fail_if_called(*_args, **_kwargs):
            raise AssertionError("HuggingFaceWeightsDownloader must not be constructed when a verified cache exists")

        monkeypatch.setattr("training.HuggingFaceWeightsDownloader", fail_if_called)

        result = module._ensure_weights_downloaded()

        assert result == str(engine_dir)

    def test_downloads_via_the_real_registry_when_no_cache_exists(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WAN22_MODELS_CACHE_ROOT", str(tmp_path / "cache"))
        monkeypatch.setenv("HF_TOKEN", "fake-token")
        module = _load_module()

        calls: list[dict] = []

        class FakeDownloader:
            def __init__(self, *, cache_root, hf_token):
                calls.append({"cache_root": cache_root, "hf_token": hf_token})

            def download(self, entry):
                local_dir = tmp_path / "downloaded"
                local_dir.mkdir()
                (local_dir / "model_index.json").write_text("{}")
                return DownloadManifest(
                    engine_id=entry.engine_id, repo_id=entry.download.repo_id, revision=entry.download.revision,
                    local_dir=str(local_dir), files={}, downloaded_at="2026-01-01T00:00:00+00:00",
                )

        monkeypatch.setattr("training.HuggingFaceWeightsDownloader", FakeDownloader)

        result = module._ensure_weights_downloaded()

        assert result == str(tmp_path / "downloaded")
        assert calls == [{"cache_root": str(tmp_path / "cache"), "hf_token": "fake-token"}]

    def test_caches_the_result_across_calls_within_one_worker_process(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WAN22_MODELS_CACHE_ROOT", str(tmp_path / "cache"))
        module = _load_module()

        call_count = {"n": 0}

        class FakeDownloader:
            def __init__(self, *, cache_root, hf_token):
                pass

            def download(self, entry):
                call_count["n"] += 1
                local_dir = tmp_path / "downloaded"
                local_dir.mkdir(exist_ok=True)
                return DownloadManifest(
                    engine_id=entry.engine_id, repo_id=entry.download.repo_id, revision=entry.download.revision,
                    local_dir=str(local_dir), files={}, downloaded_at="2026-01-01T00:00:00+00:00",
                )

        monkeypatch.setattr("training.HuggingFaceWeightsDownloader", FakeDownloader)

        first = module._ensure_weights_downloaded()
        second = module._ensure_weights_downloaded()

        assert first == second
        assert call_count["n"] == 1


class TestBuildStorageProvider:
    def test_defaults_to_local_filesystem(self, tmp_path, monkeypatch):
        monkeypatch.setenv("STORAGE_LOCAL_ROOT", str(tmp_path / "storage"))
        module = _load_module()

        from storage_sdk import LocalFilesystemStorageProvider

        assert isinstance(module._build_storage_provider(), LocalFilesystemStorageProvider)

    def test_uses_s3_when_configured(self, monkeypatch):
        monkeypatch.setenv("STORAGE_PROVIDER", "s3")
        monkeypatch.setenv("STORAGE_BUCKET", "test-bucket")
        module = _load_module()

        from storage_sdk import S3Provider

        assert isinstance(module._build_storage_provider(), S3Provider)


class TestRun:
    def test_dispatches_job_input_and_returns_output_uri(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WAN22_OUTPUT_DIR", str(tmp_path / "output"))
        monkeypatch.setenv("STORAGE_LOCAL_ROOT", str(tmp_path / "storage"))
        module = _load_module()
        monkeypatch.setattr(module, "_ensure_weights_downloaded", lambda: "/fake/model/dir")

        calls: dict = {}

        def fake_generate_video(job_input, *, output_path, smoke_test, model_id, device):
            calls.update(job_input=job_input, output_path=output_path, smoke_test=smoke_test, model_id=model_id, device=device)
            output_path.write_bytes(b"fake mp4 bytes - real content asserted elsewhere")
            return {"mode": "real", "model_id": model_id}

        monkeypatch.setattr("video_engine_adapter.inference.generate_video", fake_generate_video)

        job = {
            "id": "job-abc",
            "input": {"prompt": "a lone astronaut", "width": 1280, "height": 720, "num_frames": 58, "fps": 16},
        }

        result = module.run(job)

        assert calls["job_input"] == job["input"]
        assert calls["smoke_test"] is False
        assert calls["model_id"] == "/fake/model/dir"
        assert result["engine_metadata"] == {"mode": "real", "model_id": "/fake/model/dir"}
        assert result["output_uri"].startswith("file://")
        assert result["output_uri"].endswith("job-abc.mp4")

    def test_uses_a_generated_id_when_job_has_none(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WAN22_OUTPUT_DIR", str(tmp_path / "output"))
        monkeypatch.setenv("STORAGE_LOCAL_ROOT", str(tmp_path / "storage"))
        module = _load_module()
        monkeypatch.setattr(module, "_ensure_weights_downloaded", lambda: "/fake/model/dir")

        def fake_generate_video(job_input, *, output_path, smoke_test, model_id, device):
            output_path.write_bytes(b"x")
            return {}

        monkeypatch.setattr("video_engine_adapter.inference.generate_video", fake_generate_video)

        result = module.run({"input": {"prompt": "x", "width": 64, "height": 64, "num_frames": 9, "fps": 8}})

        assert result["output_uri"].startswith("file://")
