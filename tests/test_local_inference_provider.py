"""Tests for services/video-engine-adapter's LocalInferenceProvider -
the real (never mocked) IComputeProvider that runs
video_engine_adapter.inference.generate_video synchronously in
submit(), unlike LocalProvider which only ever writes a JSON stub.
Requires the video-engine-adapter[real-inference] extra; skipped
entirely when it is not installed (see test_video_engine_wan_inference.py).
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("torch")
pytest.importorskip("diffusers")

from video_engine_adapter.compute import LocalInferenceProvider  # noqa: E402
from video_engine_sdk import ComputeJobStatus, ComputeResourceRequirements, EngineJobPayload  # noqa: E402

_PAYLOAD = EngineJobPayload(
    container_image="sallehly/wan21-worker:2.1.0",
    input={
        "task": "t2v", "prompt": "a lone astronaut in a glowing forest", "negative_prompt": "blurry",
        "width": 1280, "height": 720, "num_frames": 58, "fps": 16, "motion_strength": 45.0,
        "guidance_scale": 6.0, "sampling_steps": 40, "seed": 7,
    },
    resources=ComputeResourceRequirements(min_vram_gb=24.0, gpu_count=1, timeout_sec=900),
)


class TestLocalInferenceProvider:
    def test_submit_writes_a_real_mp4_and_succeeds(self, tmp_path):
        provider = LocalInferenceProvider(output_dir=str(tmp_path), smoke_test=True, seed=7)

        handle = provider.submit(_PAYLOAD)

        assert provider.get_status(handle) == ComputeJobStatus.SUCCEEDED
        output = provider.fetch_output(handle)
        assert output.output_uri.startswith("file://")
        video_path = output.output_uri.removeprefix("file://")
        with open(video_path, "rb") as fh:
            assert b"ftyp" in fh.read(12)
        assert output.engine_metadata["provider"] == "local-inference"
        assert output.engine_metadata["mode"] == "smoke_test"

    def test_fetch_output_metadata_matches_written_sidecar(self, tmp_path):
        provider = LocalInferenceProvider(output_dir=str(tmp_path), smoke_test=True, seed=0)
        handle = provider.submit(_PAYLOAD)

        sidecar = json.loads((tmp_path / f"{handle.external_job_id}.json").read_text())
        output = provider.fetch_output(handle)

        assert output.engine_metadata == sidecar

    def test_get_status_is_failed_after_cancel(self, tmp_path):
        provider = LocalInferenceProvider(output_dir=str(tmp_path), smoke_test=True, seed=0)
        handle = provider.submit(_PAYLOAD)
        assert provider.get_status(handle) == ComputeJobStatus.SUCCEEDED

        provider.cancel(handle)

        assert provider.get_status(handle) == ComputeJobStatus.FAILED

    def test_submit_recreates_output_dir_if_removed_after_construction(self, tmp_path):
        # Same regression this repo already guards for LocalProvider
        # (tests/test_local_provider.py) - a long-running process must
        # not permanently fail just because its scratch dir was cleared.
        import shutil

        output_dir = tmp_path / "local-inference-output"
        provider = LocalInferenceProvider(output_dir=str(output_dir), smoke_test=True, seed=0)
        assert output_dir.exists()
        shutil.rmtree(output_dir)

        handle = provider.submit(_PAYLOAD)

        assert output_dir.exists()
        assert provider.get_status(handle) == ComputeJobStatus.SUCCEEDED

    def test_real_mode_without_model_id_propagates_a_clear_error(self, tmp_path):
        from video_engine_adapter.inference import WanInferenceUnavailableError

        provider = LocalInferenceProvider(output_dir=str(tmp_path), smoke_test=False, model_id=None)

        with pytest.raises(WanInferenceUnavailableError, match="model_id"):
            provider.submit(_PAYLOAD)
