"""Tests for services/video-engine-adapter/src/video_engine_adapter/inference/wan_inference.py -
the real (never mocked) Wan text-to-video generation code. Requires the
video-engine-adapter[real-inference] extra (torch/diffusers/transformers);
skipped entirely when it is not installed, same convention as
tests/test_training_wan22_diffusers_backend.py. Runs a real (tiny-scale)
WanPipeline forward pass + real VAE decode + real mp4 export - CPU-only,
seconds, no GPU or real Wan2.1/2.2 weights.
"""

from __future__ import annotations

import pytest

pytest.importorskip("torch")
pytest.importorskip("diffusers")

from video_engine_adapter.inference import (  # noqa: E402
    WanInferenceUnavailableError,
    build_smoke_test_pipeline,
    generate_video,
)

_JOB_INPUT = {
    "task": "t2v",
    "prompt": "Opening hook establishing the subject. general video",
    "negative_prompt": "blurry, low quality, distorted anatomy, extra limbs",
    "width": 1280,
    "height": 720,
    "num_frames": 58,
    "fps": 16,
    "motion_strength": 45.0,
    "guidance_scale": 6.0,
    "sampling_steps": 40,
    "seed": 42,
}


class TestBuildSmokeTestPipeline:
    def test_builds_a_real_wan_pipeline(self):
        pipeline = build_smoke_test_pipeline(seed=0)
        from diffusers import WanPipeline

        assert isinstance(pipeline, WanPipeline)


class TestGenerateVideo:
    def test_produces_a_real_playable_mp4_file(self, tmp_path):
        output_path = tmp_path / "shot.mp4"

        result = generate_video(_JOB_INPUT, output_path=output_path, smoke_test=True)

        assert output_path.is_file()
        assert output_path.stat().st_size > 0
        with output_path.open("rb") as handle:
            header = handle.read(12)
        assert b"ftyp" in header  # real ISO-BMFF/MP4 container signature
        assert result["mode"] == "smoke_test"
        assert result["requested_resolution"] == "1280x720"
        assert result["actual_resolution"] != "1280x720"  # clamped to smoke scale, documented in the result
        # Added per eval/reports/0006 - a real per-step latent-norm
        # trace, one entry per denoising step, used to diagnose whether
        # `latents` actually changes meaningfully during generation.
        assert len(result["step_latent_norms"]) == result["num_inference_steps"]
        assert all(isinstance(v, float) for v in result["step_latent_norms"])

    def test_same_seed_produces_identical_output(self, tmp_path):
        path_a = tmp_path / "a.mp4"
        path_b = tmp_path / "b.mp4"
        generate_video(_JOB_INPUT, output_path=path_a, smoke_test=True, seed=7)
        generate_video(_JOB_INPUT, output_path=path_b, smoke_test=True, seed=7)

        assert path_a.read_bytes() == path_b.read_bytes()

    def test_real_mode_without_model_id_raises_clearly(self, tmp_path):
        with pytest.raises(WanInferenceUnavailableError, match="model_id"):
            generate_video(_JOB_INPUT, output_path=tmp_path / "shot.mp4", smoke_test=False, model_id=None)

    def test_real_mode_requires_cuda_and_fails_fast_without_it(self, tmp_path, monkeypatch):
        import torch

        monkeypatch.setattr(torch.cuda, "is_available", lambda: False)

        with pytest.raises(WanInferenceUnavailableError, match="CUDA"):
            generate_video(
                _JOB_INPUT, output_path=tmp_path / "shot.mp4", smoke_test=False,
                model_id="Wan-AI/Wan2.1-T2V-1.3B-Diffusers", device="auto",
            )
