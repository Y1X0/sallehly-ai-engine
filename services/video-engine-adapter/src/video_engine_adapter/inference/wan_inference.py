"""Real Wan2.1/2.2 text-to-video inference - the piece
`workers/gpu-worker/handler.py::run()` used to be a bare
`NotImplementedError` stub for, and what `LocalInferenceProvider`
(../compute/local_inference_provider.py) calls in-process for a
zero-credentials, zero-external-GPU real generation path.

Two real (never mocked) modes:

- `smoke_test=True` (default): builds every `WanPipeline` component from
  the real `diffusers`/`transformers` classes - `WanTransformer3DModel`,
  `AutoencoderKLWan`, `UMT5EncoderModel`, a real (if tiny, in-process,
  no-network) tokenizer, `FlowMatchEulerDiscreteScheduler` - at a scale
  of tens of thousands of parameters instead of billions, and always
  generates at a small fixed resolution (`_SMOKE_HEIGHT`/`_SMOKE_WIDTH`/
  `_SMOKE_NUM_FRAMES`) regardless of what the job payload requested.
  This is a genuine, complete forward pass through the real denoising
  loop and real VAE decode - same mechanism verified end-to-end before
  being committed here (see this module's tests) - not a stub. It
  proves the generation pipeline is real code; it does not, and cannot,
  prove real Wan output quality (see `_SMOKE_TEST_NOTE`).
- `smoke_test=False`: loads a real, full-scale Wan2.1/2.2 checkpoint via
  `WanPipeline.from_pretrained(model_id)` and requires a real CUDA GPU
  (never silently falls back to CPU - same fail-fast convention as
  services/training/entrypoints/wan22_lora_train.py's own
  `_resolve_device`). Needs real Hugging Face network access to
  download weights the first time - untestable in this sandbox (its own
  network egress blocks huggingface.co, a previously-documented
  limitation, see docs/EXECUTION_PLAN_FIRST_GPU_RUN.md), but this is the
  same real code a real GPU machine or a real RunPod worker runs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import torch
except ImportError:  # pragma: no cover - exercised via WanInferenceUnavailableError below
    torch = None  # type: ignore[assignment]

_MISSING_DEPS_MESSAGE = (
    "video-engine-adapter[real-inference] extra is not installed - torch/diffusers/transformers "
    "are required for real Wan inference. Install with `uv sync --all-packages --extra real-inference` "
    "or `pip install \"video-engine-adapter[real-inference]\"`."
)

# Verified by hand (not guessed) in an isolated probe before being
# committed here: these dimensions match diffusers.AutoencoderKLWan's
# real assumed scale factors (vae_scale_factor_spatial=8, temporal=4)
# with the *number* of down/up-sample stages unchanged from the real
# Wan2.1 VAE (dim_mult has 4 entries -> 3 spatial-downsample
# transitions = 2**3 = 8; temperal_downsample has 2 True entries =
# 2**2 = 4) - only the channel width (base_dim) and block count are
# shrunk. Getting this wrong produces a shape mismatch inside
# WanPipeline's internal latent-size math, not a silent wrong answer.
_TINY_VAE_KWARGS: dict[str, Any] = {
    "base_dim": 4,
    "z_dim": 16,
    "dim_mult": [1, 1, 1, 1],
    "num_res_blocks": 1,
    "attn_scales": [],
    "temperal_downsample": [False, True, True],
    "latents_mean": [0.0] * 16,
    "latents_std": [1.0] * 16,
}
_TINY_TRANSFORMER_KWARGS: dict[str, Any] = {
    "patch_size": (1, 2, 2),
    "num_attention_heads": 2,
    "attention_head_dim": 16,
    "in_channels": 16,
    "out_channels": 16,
    "text_dim": 32,
    "freq_dim": 16,
    "ffn_dim": 32,
    "num_layers": 1,
    "cross_attn_norm": True,
    "qk_norm": "rms_norm_across_heads",
    "rope_max_seq_len": 32,
}
_TINY_T5_KWARGS: dict[str, Any] = {
    "vocab_size": 128,
    "d_model": 32,
    "d_ff": 64,
    "num_layers": 1,
    "num_heads": 2,
    "relative_attention_num_buckets": 4,
    "is_encoder_decoder": False,
}
# Covers the words Wan21Adapter's own generated prompts/negative-prompts
# actually use (services/video-engine-adapter/.../wan21_adapter.py) -
# enough for a real (if tiny, fixed-vocabulary) tokenizer to run without
# any network access to a real pretrained tokenizer. Unknown words map
# to [UNK], same as any real tokenizer's out-of-vocabulary handling.
_TINY_VOCAB_WORDS = (
    "a the of in on at to and or with for scene shot camera lens motion "
    "video image frame lighting light dark bright color colour still moving "
    "wide medium close up down left right pan tilt dolly zoom static slow fast "
    "high low quality blurry distorted extra limbs anatomy inconsistent flickering "
    "warped geometry smooth natural forest moon alien astronaut lone glowing "
    "discovers general opening hook establishing subject development core idea "
    "product story closing beat brand resolution eye level medium shot"
).split()

# The tiny transformer's rope_max_seq_len=32 (and the O(n^2) attention
# cost of any transformer, tiny or not) means this smoke pipeline can
# only run at a small, fixed resolution - never the job's actual
# requested width/height/num_frames (verified by hand: 1280x720/58
# frames overflows the tiny transformer's RoPE table; 64x64/9 frames
# does not). Real full-scale generation (smoke_test=False) uses the
# job's real values instead - see generate_video().
_SMOKE_HEIGHT = 64
_SMOKE_WIDTH = 64
_SMOKE_NUM_FRAMES = 9
_SMOKE_TEST_INFERENCE_STEPS = 3
_SMOKE_TEST_NOTE = (
    "Tiny, randomly-initialized-but-real WanPipeline (real WanTransformer3DModel, "
    "AutoencoderKLWan, UMT5EncoderModel, tokenizer, FlowMatchEulerDiscreteScheduler) run at a "
    f"fixed {_SMOKE_WIDTH}x{_SMOKE_HEIGHT}/{_SMOKE_NUM_FRAMES}-frame smoke scale, not the "
    "requested resolution. Proves the real generation mechanism end-to-end (real denoising loop, "
    "real VAE decode) - does not, and cannot, prove real Wan2.1/2.2 output quality. Real "
    "full-scale generation needs a real model_id (HF weights) and a real GPU - see "
    "build_real_pipeline() / COMPUTE_PROVIDER=runpod."
)


class WanInferenceUnavailableError(Exception):
    """Raised when real Wan inference cannot run right now: the
    real-inference extra isn't installed, a real (non-smoke) request
    has no CUDA GPU available, or a real request is missing a
    model_id. Always carries a human-readable reason - this is what
    surfaces to the demo UI / GenerationJob.error_message instead of a
    silent mock success (see LocalInferenceProvider)."""


def _require_torch() -> None:
    if torch is None:
        raise WanInferenceUnavailableError(_MISSING_DEPS_MESSAGE)


def _resolve_device(device: str) -> str:
    """Same fail-fast, never-silently-CPU convention as
    services/training/entrypoints/wan22_lora_train.py's own
    `_resolve_device`: 'auto'/'cuda' require a real CUDA GPU for real
    (non-smoke) inference and refuse to run otherwise - a real
    multi-billion-parameter Wan model on CPU would not just be slow, it
    would misrepresent "real inference" as usable when it isn't."""
    if device == "cpu":
        return "cpu"
    _require_torch()
    if device in ("auto", "cuda"):
        if not torch.cuda.is_available():
            raise WanInferenceUnavailableError(
                f"device={device!r} requires a CUDA-capable GPU for real (non-smoke) Wan inference, "
                "but torch.cuda.is_available() is False in this environment. Set device='cpu' only "
                "for the smoke-test path (smoke_test=True), which never needs a GPU."
            )
        return "cuda"
    return device


def _build_tiny_tokenizer() -> Any:
    try:
        from tokenizers import Tokenizer
        from tokenizers.models import WordLevel
        from tokenizers.pre_tokenizers import Whitespace
        from transformers import PreTrainedTokenizerFast
    except ImportError as exc:
        raise WanInferenceUnavailableError(_MISSING_DEPS_MESSAGE) from exc

    vocab = {"[UNK]": 0, "[PAD]": 1}
    for word in dict.fromkeys(_TINY_VOCAB_WORDS):
        vocab.setdefault(word, len(vocab))
    tokenizer_model = Tokenizer(WordLevel(vocab=vocab, unk_token="[UNK]"))
    tokenizer_model.pre_tokenizer = Whitespace()
    return PreTrainedTokenizerFast(tokenizer_object=tokenizer_model, unk_token="[UNK]", pad_token="[PAD]")


def build_smoke_test_pipeline(seed: int = 0) -> Any:
    """A tiny-but-real `diffusers.WanPipeline` - see this module's
    docstring for exactly what is and isn't proven by running it."""
    _require_torch()
    try:
        from diffusers import WanPipeline
        from diffusers.models.autoencoders.autoencoder_kl_wan import AutoencoderKLWan
        from diffusers.models.transformers.transformer_wan import WanTransformer3DModel
        from diffusers.schedulers.scheduling_flow_match_euler_discrete import FlowMatchEulerDiscreteScheduler
        from transformers import T5Config, UMT5EncoderModel
    except ImportError as exc:
        raise WanInferenceUnavailableError(_MISSING_DEPS_MESSAGE) from exc

    torch.manual_seed(seed)
    vae = AutoencoderKLWan(**_TINY_VAE_KWARGS)
    transformer = WanTransformer3DModel(**_TINY_TRANSFORMER_KWARGS)
    text_encoder = UMT5EncoderModel(T5Config(**_TINY_T5_KWARGS))
    tokenizer = _build_tiny_tokenizer()
    scheduler = FlowMatchEulerDiscreteScheduler()
    pipeline = WanPipeline(
        tokenizer=tokenizer, text_encoder=text_encoder, vae=vae, scheduler=scheduler, transformer=transformer,
    )
    return pipeline.to("cpu")


def build_real_pipeline(model_id: str, *, device: str = "cuda") -> Any:
    """Loads a real, full-scale Wan2.1/2.2 `WanPipeline` from real HF
    Hub weights (or a local directory already populated by
    `training.hf_download`). Requires real network access the first
    time (tens of GB) and a real CUDA GPU to run at a usable speed -
    this is the same real code a real RunPod worker
    (workers/gpu-worker/handler.py) or a real local GPU machine runs;
    it has not been exercised against real weights in this sandbox (no
    GPU, no Hugging Face network access here - a previously documented
    sandbox-only limitation, see docs/EXECUTION_PLAN_FIRST_GPU_RUN.md)."""
    _require_torch()
    resolved_device = _resolve_device(device)
    try:
        from diffusers import WanPipeline
    except ImportError as exc:
        raise WanInferenceUnavailableError(_MISSING_DEPS_MESSAGE) from exc

    pipeline_dtype = torch.bfloat16
    if resolved_device == "cuda" and not torch.cuda.is_bf16_supported():
        # Confirmed by hand on a real Kaggle GPU run (30288629219, right
        # after the cpu-offload fix above resolved the prior OOM): loading
        # in bf16 on an older CUDA architecture (Kaggle's free tier can
        # assign a Pascal P100, which has no bf16 tensor-core support,
        # instead of a T4) fails with "CUDA error: no kernel image is
        # available for execution on the device" - there is no compiled
        # bf16 kernel for that architecture. fp16 is supported on every
        # CUDA GPU Kaggle offers, with no precision-quality difference
        # that matters here (this is a hardware-compatibility fallback,
        # not a quality choice).
        pipeline_dtype = torch.float16
    pipeline = WanPipeline.from_pretrained(model_id, torch_dtype=pipeline_dtype)
    if resolved_device == "cuda":
        # A full bf16 Wan2.2-TI2V-5B pipeline (transformer + text encoder +
        # VAE) left resident on GPU via a plain .to("cuda") consumes ~15.6GB
        # by itself - confirmed by hand on real Kaggle GPU runs
        # (30284984066, 30286719822): both left only ~33MiB free and failed
        # on an 18MiB allocation during generation, with byte-identical
        # numbers regardless of num_frames (17 vs 9). That proves the
        # ceiling is the resident pipeline's own weight footprint, not
        # per-step activation memory that scales with frame count.
        # enable_model_cpu_offload() alone (whole submodules moved between
        # CPU/GPU) still hit a real CUDA memory-allocation failure on a
        # pinned T4 (run 30299011624: "CUBLAS_STATUS_ALLOC_FAILED" -
        # cuBLAS's own error for "no memory left for its workspace", the
        # same underlying condition as an OOM, just reported through a
        # different call path). enable_sequential_cpu_offload() is
        # diffusers' own, more aggressive built-in offload mode - it moves
        # individual weight tensors to GPU only for their exact forward
        # call instead of whole submodules, trading some speed for a much
        # smaller resident footprint. enable_attention_slicing() is a
        # second, complementary built-in toggle that reduces the peak
        # memory attention computation itself needs. Neither changes
        # precision, resolution, or output - both are standard diffusers
        # memory-management options, not new capabilities of this engine.
        pipeline.enable_sequential_cpu_offload()
        pipeline.enable_attention_slicing()
        # Sequential offload fixed the resident-weight footprint (run
        # 30301127047 confirmed only 5.43GB in use at failure time, well
        # under the T4's 14.56GB), but a real, single activation
        # allocation still failed: OutOfMemoryError, "Tried to allocate
        # 13.45 GiB" with only 9.13GiB free - the full 17-frame,
        # 960x544 video being decoded by the VAE in one shot.
        # AutoencoderKLWan.enable_tiling()/enable_slicing() are
        # diffusers' own built-in VAE memory options for exactly this:
        # tiling splits a large decode into smaller spatial tiles, and
        # slicing decodes one frame group at a time, instead of one
        # huge tensor. Neither changes precision, resolution, or output.
        pipeline.vae.enable_tiling()
        pipeline.vae.enable_slicing()
        return pipeline
    return pipeline.to(resolved_device)


def generate_video(
    job_input: dict[str, Any],
    *,
    output_path: Path,
    smoke_test: bool = True,
    model_id: str | None = None,
    device: str = "cpu",
    seed: int | None = None,
) -> dict[str, Any]:
    """Runs one real Wan text-to-video generation from an
    `EngineJobPayload.input` dict (the shape `Wan21Adapter.build_job_payload`
    produces: prompt/negative_prompt/width/height/num_frames/fps/
    guidance_scale/sampling_steps/seed/...) and writes a real `.mp4` to
    `output_path` via `diffusers.utils.export_to_video`. Returns metadata
    describing what actually ran - `LocalInferenceProvider` and
    `workers/gpu-worker/handler.py` attach this as `engine_metadata` so
    callers can always tell smoke-scale output from real output."""
    _require_torch()
    resolved_seed = seed if seed is not None else int(job_input.get("seed") or 0)

    if smoke_test:
        pipeline = build_smoke_test_pipeline(seed=resolved_seed)
        height, width, num_frames = _SMOKE_HEIGHT, _SMOKE_WIDTH, _SMOKE_NUM_FRAMES
        num_inference_steps = min(int(job_input.get("sampling_steps", _SMOKE_TEST_INFERENCE_STEPS)), _SMOKE_TEST_INFERENCE_STEPS)
        mode = "smoke_test"
        note = _SMOKE_TEST_NOTE
        resolved_model_id = "tiny-smoke-wan"
        resolved_device = "cpu"
    else:
        if not model_id:
            raise WanInferenceUnavailableError(
                "Real (non-smoke) Wan inference requires a model_id (e.g. a real HF Hub Wan2.1/2.2 "
                "repo id, or a local directory from training.hf_download.resolve_local_weights)."
            )
        pipeline = build_real_pipeline(model_id, device=device)
        height, width, num_frames = int(job_input["height"]), int(job_input["width"]), int(job_input["num_frames"])
        num_inference_steps = int(job_input.get("sampling_steps", 40))
        mode = "real"
        note = f"Real Wan inference from model_id={model_id!r}."
        resolved_model_id = model_id
        resolved_device = _resolve_device(device)

    generator = torch.Generator(device="cpu").manual_seed(resolved_seed)
    result = pipeline(
        prompt=job_input["prompt"],
        negative_prompt=job_input.get("negative_prompt"),
        height=height,
        width=width,
        num_frames=num_frames,
        num_inference_steps=num_inference_steps,
        guidance_scale=float(job_input.get("guidance_scale", 1.0)),
        generator=generator,
    )
    frames = result.frames[0]

    from diffusers.utils import export_to_video

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fps = int(job_input.get("fps", 16))
    export_to_video(list(frames), str(output_path), fps=fps)

    return {
        "mode": mode,
        "note": note,
        "model_id": resolved_model_id,
        "device": resolved_device,
        "seed": resolved_seed,
        "requested_resolution": f"{job_input.get('width')}x{job_input.get('height')}",
        "actual_resolution": f"{width}x{height}",
        "num_frames": num_frames,
        "fps": fps,
        "num_inference_steps": num_inference_steps,
    }
