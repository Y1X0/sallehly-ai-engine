#!/usr/bin/env python3
"""Kaggle kernel script: runs one real Wan2.1/2.2 text-to-video
inference on a real Kaggle free GPU (P100/T4) and writes a real `.mp4`
under `/kaggle/working/output/` (the directory `kaggle kernels output`
downloads after the kernel finishes).

This is the inference counterpart to
services/training/entrypoints/kaggle_kernel_runner.py - same real
mechanics (verify CUDA, clone this repo at a pinned git ref, install
only what's missing, never touch Kaggle's preinstalled CUDA-enabled
torch build), but calls the platform's own, already-real
video_engine_adapter.inference.wan_inference.generate_video() instead
of a training loop. Nothing here is a new inference implementation -
it is the exact same function LocalInferenceProvider and
workers/gpu-worker/handler.py call, just given a real GPU and a real
model_id for the first time (see docs/PRODUCTION_READINESS_CHECKLIST.md
"Deferred").

Pushed by infra/kaggle/dispatch_inference.py as this kernel's `code_file`,
with a Kaggle dataset attached (mounted read-only under
/kaggle/input/<slug>/) containing:
  - git_ref.txt          - which branch/commit to clone (see below)
  - inference_request.json - prompt + generation parameters (the
                              EngineJobPayload.input shape
                              wan_inference.generate_video() expects,
                              plus model_id/seed)

Real, honest constraint carried over from
models/wan2.2-ti2v-5b/capability_manifest.yaml: this engine's own
gpu_requirements.min_vram_gb is 16 - Kaggle's free P100/T4 also have
16GB. This may fit or may not (no block-swap/fp8 trick is applied
here, plain bf16 full precision, exactly what generate_video() already
does) - a real CUDA OOM is a legitimate, informative real result, not
a bug in this script; see infra/kaggle/README.md.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import traceback
from pathlib import Path

_REPO_URL = "https://github.com/y1x0/sallehly-ai-engine.git"

# Mirrors services/video-engine-adapter/pyproject.toml's `real-inference`
# extra, minus torch itself - Kaggle's kernel image ships its own
# CUDA-enabled torch build preinstalled (see
# services/training/entrypoints/kaggle_kernel_runner.py's own
# _install_missing_packages docstring for why this must never be
# reinstalled). `httpx` is video-engine-adapter's own base dependency
# (imported transitively via video_engine_adapter.compute.RunPodProvider
# at package-import time, even though this script never uses it) -
# included here so `--no-deps` installs below don't leave it missing.
_MISSING_OK_PACKAGES: dict[str, str] = {
    "diffusers": "diffusers>=0.31",
    "transformers": "transformers>=4.44",
    "tokenizers": "tokenizers>=0.19",
    "imageio": "imageio>=2.34",
    "imageio_ffmpeg": "imageio-ffmpeg>=0.5",
    "httpx": "httpx>=0.27",
}


def _run(args: list[str]) -> None:
    print(f"$ {' '.join(args)}", flush=True)
    subprocess.run(args, check=True)


def _verify_cuda_available() -> None:
    """Same fail-fast convention as the training kernel runner and
    wan_inference._resolve_device(): refuses to silently run on CPU."""
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError(
            "torch.cuda.is_available() is False on this Kaggle kernel - no CUDA GPU is attached. "
            "Check this kernel's Settings -> Accelerator (must be GPU T4x2 or P100) and re-push."
        )


def _install_missing_packages(repo_dir: Path) -> None:
    _run([
        sys.executable, "-m", "pip", "install", "--quiet", "--no-deps",
        "-e", str(repo_dir / "packages" / "video-engine-sdk"),
        "-e", str(repo_dir / "packages" / "config-sdk"),
        "-e", str(repo_dir / "services" / "video-engine-adapter"),
    ])
    missing = [
        requirement
        for module_name, requirement in _MISSING_OK_PACKAGES.items()
        if importlib.util.find_spec(module_name) is None
    ]
    if missing:
        _run([sys.executable, "-m", "pip", "install", "--quiet", "--no-deps", *missing])


def main(
    *,
    repo_dir: Path = Path("/kaggle/working/repo"),
    kaggle_input_root: Path = Path("/kaggle/input"),
    kaggle_working_root: Path = Path("/kaggle/working"),
    clone: bool = True,
) -> int:
    """`repo_dir`/`kaggle_input_root`/`kaggle_working_root`/`clone` are
    only ever overridden by tests - a real Kaggle kernel invocation
    (`python kaggle_inference_kernel_runner.py`, no args) always uses
    the real Kaggle paths and always clones fresh (no persistent disk
    between kernel runs)."""
    # Kaggle's own /kaggle/input layout is not fixed: older kernels mount a
    # dataset directly at /kaggle/input/<dataset-slug>/, but a real run
    # (30279700088) showed Kaggle now nests it one level deeper, under
    # /kaggle/input/datasets/<dataset-slug>/ - a plain `glob("*")` picked
    # the "datasets" parent itself (sorted first) instead of descending into
    # it, so git_ref.txt/inference_request.json were never found even
    # though the dataset really was attached. Searching recursively for the
    # file this kernel actually needs is robust to either layout.
    git_ref_matches = sorted(kaggle_input_root.rglob("git_ref.txt"))
    if not git_ref_matches:
        raise RuntimeError(
            f"No git_ref.txt found anywhere under {kaggle_input_root} - dispatch_inference.py must attach "
            "the job's git_ref.txt/inference_request.json dataset via KernelPushConfig.dataset_sources; "
            "this kernel was not pushed with one."
        )
    input_dir = git_ref_matches[0].parent
    git_ref_path = input_dir / "git_ref.txt"
    request_path = input_dir / "inference_request.json"
    if not request_path.is_file():
        raise RuntimeError(
            f"Found {git_ref_path} but not {request_path} in the mounted dataset - "
            "dispatch_inference.py builds both; this kernel was pushed without them."
        )
    git_ref = git_ref_path.read_text().strip()
    request = json.loads(request_path.read_text())

    _verify_cuda_available()

    if clone:
        _run(["git", "clone", "--depth", "1", "--branch", git_ref, _REPO_URL, str(repo_dir)])
        _install_missing_packages(repo_dir)

    sys.path.insert(0, str(repo_dir / "services" / "video-engine-adapter" / "src"))
    sys.path.insert(0, str(repo_dir / "packages" / "video-engine-sdk" / "src"))
    sys.path.insert(0, str(repo_dir / "packages" / "config-sdk" / "src"))
    from video_engine_adapter.inference.wan_inference import generate_video  # noqa: E402

    output_dir = kaggle_working_root / "output"
    output_path = output_dir / "video.mp4"
    job_input = request["job_input"]
    metadata = generate_video(
        job_input,
        output_path=output_path,
        smoke_test=False,
        model_id=request["model_id"],
        device="cuda",
        seed=request.get("seed"),
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))
    print(f"\nInference complete: {output_path}")
    print(json.dumps(metadata, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 - this is the top-level Kaggle kernel entrypoint;
        # the real reason (CUDA OOM, missing weights repo, bad request JSON, etc.) must reach
        # this kernel's own log output and metadata.json instead of a bare traceback getting lost
        # once the kernel finishes - fetch_inference_result.py reads error.json when metadata.json
        # is absent, so a caller always gets a real, specific reason instead of "Internal error".
        error_report = {"error_type": type(exc).__name__, "error_message": str(exc)}
        Path("/kaggle/working/output").mkdir(parents=True, exist_ok=True)
        Path("/kaggle/working/output/error.json").write_text(json.dumps(error_report, indent=2))
        print(f"kaggle_inference_kernel_runner.py: FAILED - {type(exc).__name__}: {exc}", file=sys.stderr)
        traceback.print_exc()
        raise SystemExit(1) from exc
