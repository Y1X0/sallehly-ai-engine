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
    if pipeline_dtype == torch.float16:
        # Confirmed by hand on a real Kaggle GPU run (30303715804): the
        # kernel completed and wrote a real video.mp4 with no crash, but
        # every frame decoded to near-flat, muddy, low-contrast noise
        # (checked by hand: RGB channel means ~90/85/78, std ~10-14,
        # pixel range compressed to roughly 34-130 out of 0-255) instead
        # of the requested scene - not a crash, a silent numerical
        # failure. This is the well-documented diffusers/Stable-Diffusion
        # failure mode where decoding the VAE in fp16 overflows its
        # narrow exponent range inside GroupNorm/attention layers,
        # producing garbage pixels; bf16 has fp32's exponent range and
        # does not have this problem, but bf16 itself isn't supported on
        # this GPU (see the fp16 fallback above). WanPipeline's own
        # decode step (`latents.to(self.vae.dtype)` in
        # WanPipeline.__call__) already casts whatever dtype the VAE
        # module is in, so upcasting only the VAE submodule to fp32
        # keeps the transformer/text-encoder in fp16 (preserving the
        # memory savings above) while decoding numerically correctly -
        # the same "upcast just the VAE" pattern diffusers' own SDXL
        # pipeline uses.
        pipeline.vae = pipeline.vae.to(torch.float32)
        # eval/reports/0001-0004 traced the flat/muddy output through 4
        # real Kaggle runs: the VAE upcast above (0002) and a
        # guidance_scale 1.0->6.0 fix (0003) both measured as having
        # zero effect on the output - 0004 confirmed via metadata.json
        # that guidance_scale=6.0 genuinely reaches pipeline() and
        # reading the installed diffusers WanPipeline source confirmed
        # its CFG formula (`noise_uncond + scale*(noise_pred -
        # noise_uncond)`) is standard/correct. For CFG to be a no-op
        # despite executing for real (a real, measured +26-38% run
        # duration each time), the conditional and unconditional
        # (empty-string) prompt embeddings must be coming out nearly
        # identical - i.e. numerically degenerate regardless of input
        # text. `text_encoder` (UMT5EncoderModel, a T5-family model)
        # was never upcast in any prior fix - only the VAE was - and
        # T5-family encoders are a separately well-documented case of
        # fp16 numerical instability, the same overflow failure mode
        # already found and fixed once for the VAE, just in a
        # different submodule. `_get_t5_prompt_embeds` already casts
        # its output down to the transformer's dtype before use
        # (`prompt_embeds.to(transformer_dtype)` in WanPipeline.__call__),
        # so this only changes the precision the encoder's own forward
        # pass runs at, not memory footprint downstream - same pattern
        # as the VAE fix above.
        pipeline.text_encoder = pipeline.text_encoder.to(torch.float32)
        # eval/reports/0005: upcasting text_encoder also measured as
        # having zero effect on real Kaggle output (5th consecutive
        # byte-identical result, run 30333553288) - ruling it out the
        # same way the VAE was ruled out in 0002. VAE and text_encoder
        # are now both confirmed not to be the cause; `transformer`
        # (`WanTransformer3DModel`, 5B params) is the only fp16
        # submodule left untested, and by far the largest/most central
        # to the model's actual computation - if its own fp16 forward
        # pass overflows, that would explain every prior observation at
        # once (degenerate output regardless of VAE/text-encoder
        # precision, and CFG being a no-op regardless of guidance_scale,
        # since a saturated transformer output would swamp out whatever
        # conditioning it's given). This does carry real OOM risk (fp32
        # roughly doubles the transformer's ~10GB fp16 weight footprint
        # plus per-step activation memory, on a T4 that already needed
        # sequential offload + VAE tiling to fit) - an OOM here would
        # itself be diagnostic, not a wasted run, since it would
        # confirm the transformer is where memory/numerical pressure
        # concentrates.
        pipeline.transformer = pipeline.transformer.to(torch.float32)
        if pipeline.transformer_2 is not None:
            pipeline.transformer_2 = pipeline.transformer_2.to(torch.float32)
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
        #
        # eval/reports/0007-0008: every real Kaggle run since tiling
        # was enabled here (iterations 0002-0007 - 7 consecutive real
        # runs, spanning every precision/guidance_scale/seed
        # combination tried) produced a video whose every frame showed
        # the same fine, regular checkerboard/basket-weave texture,
        # confirmed by zooming into individual frames - not random
        # noise, a well-documented deconvolution/tiling artifact
        # signature. `enable_slicing()` (splits along the batch/frame
        # dimension) is kept - it isn't implicated in a *spatial*
        # checkerboard the way tile blending is. Disabling tiling
        # carries real OOM risk (this is exactly the option that fixed
        # the earlier "Tried to allocate 13.45 GiB" failure) - an OOM
        # here would itself be diagnostic, confirming tiling really is
        # needed for memory and pointing toward a different mitigation
        # (e.g. lower resolution/frame count) instead of tiling.
        #
        # eval/reports/0011: with tiling disabled at a *smaller*
        # resolution/frame count (480x272, 9 frames - specifically to
        # dodge the OOM), every one of the 20 `step_latent_norms` came
        # back NaN (not random, not degenerate-but-real - a complete
        # numerical failure from the very first denoising step).
        # Iteration 0007 (tiling ENABLED, 960x544, 17 frames) produced
        # real, non-NaN, monotonically-converging latent norms with the
        # exact same model-loading code - this re-enables tiling, at
        # the *same* reduced 480x272/9-frame configuration 0011 used,
        # changing only this one variable, to test directly whether
        # tiling itself is what prevents the NaN (not just a memory
        # convenience) rather than assuming it from the OOM-blocked
        # non-tiled attempts in 0008-0010.
        #
        # eval/reports/0012: confirmed by a clean, single-variable A/B
        # test - tiling ON produced all-finite step_latent_norms at the
        # *same* 480x272/9-frame config that produced all-NaN with
        # tiling off. But visual inspection of the real video showed a
        # different real artifact: regular vertical blue banding, not
        # random noise, not the earlier checkerboard - consistent with
        # AutoencoderKLWan.tiled_decode()'s own tile-blending seams
        # (default tile_sample_min_width=256 against our 480px-wide
        # frame produces exactly ~2 overlapping tiles with visible
        # blend boundaries, confirmed by reading tiled_decode()'s real
        # source: `for j in range(0, width, tile_latent_stride_width)`).
        # Setting tile_sample_min_height/width (and matching strides)
        # larger than the actual frame dimensions makes that same loop
        # produce exactly ONE tile - still going through the "tiled"
        # code path (whatever in it avoids the NaN), but decoding the
        # whole frame in one pass with no real splitting or blending,
        # to test directly whether NaN-avoidance depends on which
        # function is called (tiled_decode vs decode) or on genuinely
        # splitting into >=2 tiles.
        pipeline.vae.enable_tiling(
            tile_sample_min_height=608,
            tile_sample_min_width=1024,
            tile_sample_stride_height=608,
            tile_sample_stride_width=1024,
        )
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

    resolved_prompt = job_input["prompt"]
    resolved_negative_prompt = job_input.get("negative_prompt")
    resolved_guidance_scale = float(job_input.get("guidance_scale", 1.0))

    # eval/reports/0001-0006 ruled out fp16 overflow in the VAE, text
    # encoder, and transformer (all individually upcast to fp32, all
    # measured zero effect on 6 consecutive real Kaggle runs - every
    # one producing a byte-for-byte identical video.mp4) and confirmed
    # guidance_scale/prompt genuinely reach pipeline() correctly. The
    # remaining, untested question is whether the denoising loop is
    # actually updating `latents` at all - if `scheduler.step()`'s
    # effective per-step update is negligible, the final decoded video
    # would be dominated almost entirely by the initial random noise
    # (always the same for seed=0, used in every prior iteration),
    # which would explain byte-identical output regardless of
    # precision, guidance_scale, or prompt. `callback_on_step_end` is
    # diffusers' own official, non-invasive hook for observing
    # intermediate tensors during generation - not a reimplementation
    # of the pipeline's internals.
    # eval/reports/0011 found step_latent_norms all came back NaN, from
    # the very first denoising step, at a reduced resolution with
    # tiling disabled - a real numerical failure, not just a
    # checkerboard artifact. A single scalar norm-per-step can't say
    # *where* the corruption first appears. `prompt_embeds`/
    # `negative_prompt_embeds` (the real text-encoder output, requested
    # alongside `latents`) are the only other tensors WanPipeline's own
    # `_callback_tensor_inputs` whitelist allows through this official,
    # non-invasive callback mechanism (`noise_pred` is not in that
    # whitelist - confirmed by a real `ValueError` when requesting it
    # against the actual diffusers class, not assumed) - but checking
    # them directly answers the "does the text encoder's own output
    # already look broken before any denoising step runs" question
    # (eval/reports/0004's still-unconfirmed hypothesis) more precisely
    # than an empty-prompt trial would.
    step_diagnostics: list[dict[str, Any]] = []

    def _tensor_report(name: str, tensor: Any) -> dict[str, Any]:
        if tensor is None:
            return {}
        is_nan = bool(torch.isnan(tensor).any().item())
        is_inf = bool(torch.isinf(tensor).any().item())
        report: dict[str, Any] = {
            f"{name}_dtype": str(tensor.dtype),
            f"{name}_shape": list(tensor.shape),
            f"{name}_isnan": is_nan,
            f"{name}_isinf": is_inf,
        }
        if not is_nan and not is_inf:
            report[f"{name}_norm"] = float(tensor.float().norm().item())
        return report

    def _record_step_diagnostics(pipe: Any, step: int, timestep: Any, callback_kwargs: dict) -> dict:
        entry: dict[str, Any] = {
            "step": step,
            "timestep": float(timestep.item()) if hasattr(timestep, "item") else timestep,
        }
        entry.update(_tensor_report("latents", callback_kwargs.get("latents")))
        entry.update(_tensor_report("prompt_embeds", callback_kwargs.get("prompt_embeds")))
        entry.update(_tensor_report("negative_prompt_embeds", callback_kwargs.get("negative_prompt_embeds")))
        sigmas = getattr(pipe.scheduler, "sigmas", None)
        if sigmas is not None and step < len(sigmas):
            entry["sigma"] = float(sigmas[step].item())
        step_diagnostics.append(entry)
        return callback_kwargs

    generator = torch.Generator(device="cpu").manual_seed(resolved_seed)
    result = pipeline(
        prompt=resolved_prompt,
        negative_prompt=resolved_negative_prompt,
        height=height,
        width=width,
        num_frames=num_frames,
        num_inference_steps=num_inference_steps,
        guidance_scale=resolved_guidance_scale,
        generator=generator,
        callback_on_step_end=_record_step_diagnostics,
        callback_on_step_end_tensor_inputs=["latents", "prompt_embeds", "negative_prompt_embeds"],
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
        # Added after eval/reports/0003 found guidance_scale=1.0->6.0
        # made zero measurable difference to real Kaggle output (a
        # byte-for-byte identical video.mp4 - see that report) - this
        # closes the "did the fix even reach pipeline()" ambiguity by
        # echoing back the exact values the real call actually used,
        # directly in every future run's metadata.json, instead of
        # having to infer them from dispatch_inference.py's CLI args.
        "prompt": resolved_prompt,
        "negative_prompt": resolved_negative_prompt,
        "guidance_scale": resolved_guidance_scale,
        # Added after eval/reports/0011 found step_latent_norms all NaN
        # from the first denoising step at a reduced resolution with
        # tiling disabled - replaced by the richer step_diagnostics
        # above (per-tensor NaN/Inf/dtype/shape/sigma at every step)
        # to pinpoint exactly which tensor first breaks, instead of
        # just knowing that something did.
        "step_diagnostics": step_diagnostics,
        # Submodule dtypes, logged directly rather than inferred - a
        # real fp16/fp32 mismatch between any two of these could
        # explain a NaN on its own (e.g. a fp16 tensor overflowing when
        # multiplied against an fp32 one, or vice versa).
        "transformer_dtype": str(pipeline.transformer.dtype) if getattr(pipeline, "transformer", None) is not None else None,
        "vae_dtype": str(pipeline.vae.dtype) if getattr(pipeline, "vae", None) is not None else None,
        "text_encoder_dtype": str(pipeline.text_encoder.dtype) if getattr(pipeline, "text_encoder", None) is not None else None,
    }
