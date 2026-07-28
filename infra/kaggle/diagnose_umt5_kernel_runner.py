#!/usr/bin/env python3
"""Kaggle kernel script: isolates Wan2.2's UMT5 text encoder completely
from the rest of `WanPipeline` - no transformer, no VAE, no
`enable_sequential_cpu_offload()` - to test the user's own next-step
hypothesis directly: eval/reports/0015-0019 pinpointed and then
confirmed (via a clean single-variable A/B, eval/reports/0019) that
`text_encoder(input_ids, attention_mask).last_hidden_state` returns an
all-zero tensor even when its own weights are proven real, healthy,
and non-meta, and even with `enable_sequential_cpu_offload()`
disabled. That result already rules out this project's own generation
code as the cause; the three remaining candidates are outside it: a
`transformers` regression affecting UMT5, `diffusers`/`WanPipeline`
calling UMT5 incorrectly, or a `transformers` version mismatch against
what Wan2.2's checkpoint expects (its `text_encoder/config.json`
declares `"transformers_version": "4.48.0.dev0"`).

This script loads `transformers.UMT5EncoderModel` and its tokenizer
directly from the same real HF Hub checkpoint
(`Wan-AI/Wan2.2-TI2V-5B-Diffusers`), completely independent of
`diffusers`/`WanPipeline`, runs one real forward pass, and reports the
result - a real, non-mocked test, but small enough (just the ~6.7B
encoder, no 5B transformer, no VAE, no offload staging) to complete in
minutes instead of the >1 hour a full `WanPipeline` run takes. No
video is produced - the only output is `output/metadata.json` (or
`output/error.json` on a real exception), matching the failure-mode
convention `kaggle_inference_kernel_runner.py` already uses.

Optionally accepts a mounted dataset with `request.json` -
`{"model_id": ..., "prompt": ..., "max_sequence_length": ...,
"transformers_version": ...}` - falling back to Wan2.2's own real
model_id/prompt/max_sequence_length if none is mounted.
`transformers_version`, if set, is installed via pip *before* any
`transformers` import, to directly test the user's own follow-up
question: does a different transformers version change this result?
"""

from __future__ import annotations

import json
import subprocess
import sys
import traceback
from pathlib import Path

_DEFAULT_MODEL_ID = "Wan-AI/Wan2.2-TI2V-5B-Diffusers"
_DEFAULT_PROMPT = "A cinematic sunset over a futuristic city, high quality"
# Matches WanPipeline.encode_prompt()'s own default (see
# eval/reports/0016/0017) - the same value the real pipeline uses.
_DEFAULT_MAX_SEQUENCE_LENGTH = 226


def _run(args: list[str]) -> None:
    print(f"$ {' '.join(args)}", flush=True)
    subprocess.run(args, check=True)


def _load_request(kaggle_input_root: Path) -> dict:
    matches = sorted(kaggle_input_root.rglob("request.json"))
    if not matches:
        print("No request.json found under kaggle_input_root - using built-in defaults.")
        return {}
    return json.loads(matches[0].read_text())


def main(*, kaggle_input_root: Path = Path("/kaggle/input"), kaggle_working_root: Path = Path("/kaggle/working")) -> int:
    request = _load_request(kaggle_input_root)
    model_id = request.get("model_id", _DEFAULT_MODEL_ID)
    prompt = request.get("prompt", _DEFAULT_PROMPT)
    max_sequence_length = int(request.get("max_sequence_length", _DEFAULT_MAX_SEQUENCE_LENGTH))
    transformers_version_override = request.get("transformers_version")

    import torch

    if not torch.cuda.is_available():
        raise RuntimeError(
            "torch.cuda.is_available() is False on this Kaggle kernel - no CUDA GPU is attached. "
            "Check this kernel's Settings -> Accelerator (must be GPU T4x2 or P100) and re-push."
        )

    if transformers_version_override:
        # Installed *before* transformers is ever imported, so this
        # process actually runs the pinned version rather than whatever
        # Kaggle's base image shipped - directly tests the user's own
        # follow-up question (does a different transformers version
        # change this result?), without needing a second script.
        _run([sys.executable, "-m", "pip", "install", "--quiet", f"transformers=={transformers_version_override}"])

    import diffusers
    import transformers
    from transformers import AutoTokenizer, UMT5EncoderModel

    print(f"torch: {torch.__version__}")
    print(f"transformers: {transformers.__version__}")
    print(f"diffusers: {diffusers.__version__}")
    print(f"model_id: {model_id}")
    print(f"prompt: {prompt!r}")
    print(f"max_sequence_length: {max_sequence_length}")

    tokenizer = AutoTokenizer.from_pretrained(model_id, subfolder="tokenizer")
    text_encoder = UMT5EncoderModel.from_pretrained(model_id, subfolder="text_encoder", torch_dtype=torch.bfloat16)
    text_encoder = text_encoder.to("cuda").eval()

    # Mirrors WanPipeline._get_t5_prompt_embeds's own real tokenizer
    # call exactly (confirmed by reading diffusers 0.37.1's source in
    # eval/reports/0015/0016) - the only difference from that method is
    # that no WanPipeline/enable_sequential_cpu_offload exists here at all.
    text_inputs = tokenizer(
        [prompt],
        padding="max_length",
        max_length=max_sequence_length,
        truncation=True,
        add_special_tokens=True,
        return_attention_mask=True,
        return_tensors="pt",
    )
    input_ids = text_inputs.input_ids.to("cuda")
    attention_mask = text_inputs.attention_mask.to("cuda")

    with torch.no_grad():
        outputs = text_encoder(input_ids=input_ids, attention_mask=attention_mask)
    last_hidden_state = outputs.last_hidden_state

    result = {
        "torch_version": torch.__version__,
        "transformers_version": transformers.__version__,
        "diffusers_version": diffusers.__version__,
        "model_id": model_id,
        "prompt": prompt,
        "max_sequence_length": max_sequence_length,
        "last_hidden_state_shape": list(last_hidden_state.shape),
        "last_hidden_state_dtype": str(last_hidden_state.dtype),
        "last_hidden_state_min": float(last_hidden_state.float().min().item()),
        "last_hidden_state_max": float(last_hidden_state.float().max().item()),
        "last_hidden_state_mean": float(last_hidden_state.float().mean().item()),
        "last_hidden_state_norm": float(last_hidden_state.float().norm().item()),
    }

    output_dir = kaggle_working_root / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "metadata.json").write_text(json.dumps(result, indent=2))
    print("\nUMT5-only diagnostic complete:")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 - top-level Kaggle kernel entrypoint; the real
        # reason must reach this kernel's own metadata/error.json output, same convention
        # as kaggle_inference_kernel_runner.py.
        error_report = {"error_type": type(exc).__name__, "error_message": str(exc)}
        Path("/kaggle/working/output").mkdir(parents=True, exist_ok=True)
        Path("/kaggle/working/output/error.json").write_text(json.dumps(error_report, indent=2))
        print(f"diagnose_umt5_kernel_runner.py: FAILED - {type(exc).__name__}: {exc}", file=sys.stderr)
        traceback.print_exc()
        raise SystemExit(1) from exc
