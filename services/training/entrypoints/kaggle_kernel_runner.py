#!/usr/bin/env python3
"""Kaggle kernel wrapper for wan22_lora_train.py.

This file exists because a plain Kaggle kernel push cannot do three
things a real training run needs: receive CLI arguments, have the
`training` package (and `models/registry.yaml`, which lives at the repo
root, outside that package) available, or keep downloaded weights
between runs (Kaggle kernels have no persistent local disk - each run
starts from a clean container). See
docs/adr/0025-kaggle-dispatch-argv-fix.md and
`training.wan22.dispatch.dispatch_via_kaggle`'s own docstring for the
full story.

What this script does, in order - all real subprocess calls, no
sys.path tricks:
  0. Verifies a CUDA GPU is actually attached (`torch.cuda.is_available()`)
     before doing anything else - fails immediately, with a clear error,
     otherwise. This kernel's entire purpose is a real GPU run; a
     misconfigured accelerator setting must not be allowed to silently
     degrade to a CPU run (see step 4's `--device auto`).
  1. Shallow-clones this repo (public, no auth needed for read access)
     at the git ref recorded in `git_ref.txt` (written by
     `dispatch_via_kaggle()` into the same mounted dataset as
     config.yaml/dataset_manifest.jsonl - a plain `git clone` with no
     `--branch` would silently pull whatever the repo's *default*
     branch happens to be, which will not contain this code until this
     work is merged there) into `/kaggle/working/repo`, and installs
     `video-engine-sdk` + `training` from it in editable mode with
     `--no-deps`, then installs only whichever of the gpu-training
     extra's dependencies aren't already importable - Kaggle's kernel
     image ships its own CUDA-enabled torch build preinstalled, and this
     never asks pip to resolve or touch `torch` at all (see
     `_install_missing_packages`'s docstring).
  2. Runs the repo's own `download_wan22_weights.py` for real, fresh,
     inside this run's container. `HF_TOKEN`, if the target repo needs
     one, must be attached to this kernel as a Kaggle Secret exposed as
     an environment variable of the same name (Kaggle Settings ->
     Secrets on the kernel) - never hardcoded here.
  3. Reads `config.yaml`/`dataset_manifest.jsonl` from the Kaggle
     dataset `dispatch_via_kaggle()` uploads and mounts read-only under
     `/kaggle/input/<slug>/` - the real substitute for CLI arguments.
  4. Runs the cloned repo's own `wan22_lora_train.py --backend real
     --device auto` against those paths, writing output/checkpoints
     under `/kaggle/working/` - the directory `kaggle kernels output`
     (and this repo's `fetch_kaggle_kernel_result.py`) downloads after
     the kernel finishes. `--device auto` itself refuses to fall back to
     CPU if CUDA somehow becomes unavailable between step 0 and here.

Pushed by `dispatch_via_kaggle()` alongside `wan22_lora_train.py`, but
does not import it - everything below runs the cloned copy as a real
subprocess, so this script itself has zero dependency on `training`
being importable in whatever environment Kaggle happens to run it in.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

_REPO_URL = "https://github.com/y1x0/sallehly-ai-engine.git"
_ENGINE_ID = "wan2.2-ti2v-5b"

# Mirrors services/training/pyproject.toml's `gpu-training` extra, minus
# torch itself: Kaggle's kernel image ships its own CUDA-enabled torch
# build preinstalled, and this list exists specifically so it is never
# reinstalled (see _install_missing_packages's docstring below).
_GPU_TRAINING_EXTRA_PACKAGES: dict[str, str] = {
    "diffusers": "diffusers>=0.31",
    "transformers": "transformers>=4.44",
    "accelerate": "accelerate>=0.33",
    "peft": "peft>=0.12",
    "safetensors": "safetensors>=0.4",
    "huggingface_hub": "huggingface_hub>=0.24",
    "imageio": "imageio>=2.34",
    "imageio_ffmpeg": "imageio-ffmpeg>=0.5",
}


def _run(args: list[str]) -> None:
    print(f"$ {' '.join(args)}", flush=True)
    subprocess.run(args, check=True)


def _verify_cuda_available() -> None:
    """Fails fast, before any install/download work, if this kernel has
    no CUDA GPU actually attached - the most severe gap the pre-first-
    real-run production audit found: a real Kaggle GPU dispatch could
    previously reach the training step and silently train on CPU
    instead (wan22_lora_train.py's --device defaulted to "cpu" and this
    wrapper never overrode it). This kernel's whole purpose is a real
    GPU run, so refusing to proceed without one is the correct failure,
    not an inconvenience - check the kernel's Settings -> Accelerator."""
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError(
            "torch.cuda.is_available() is False on this Kaggle kernel - no CUDA GPU is attached. "
            "Check this kernel's Settings -> Accelerator and re-push; refusing to silently train "
            "on CPU."
        )


def _install_missing_packages(repo_dir: Path) -> None:
    """Installs the two local packages with --no-deps so pip's
    dependency resolution never touches torch, then installs only
    whichever of the gpu-training extra's OTHER dependencies aren't
    already importable (also --no-deps).

    A plain `pip install -e "services/training[gpu-training]"` asks pip
    to satisfy that extra's own `torch>=2.3` requirement - which risks
    pip deciding to replace Kaggle's preinstalled CUDA-enabled torch
    build with an unrelated one resolved from PyPI (a real, previously-
    undetected risk: Kaggle's torch has a `+cuXXX` local version/build
    matched to its drivers and CUDA toolkit, and there's no reason to
    trust a PyPI-resolved replacement build works with that same
    hardware). Reusing Kaggle's preinstalled torch outright removes that
    risk entirely.
    """
    _run([
        sys.executable, "-m", "pip", "install", "--quiet", "--no-deps",
        "-e", str(repo_dir / "packages" / "video-engine-sdk"),
        "-e", str(repo_dir / "services" / "training"),
    ])

    missing = [
        requirement
        for module_name, requirement in _GPU_TRAINING_EXTRA_PACKAGES.items()
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
    (`python kaggle_kernel_runner.py`, no args) always uses the real
    Kaggle paths and always clones fresh."""
    # Fail fast on a misconfigured dispatch (no dataset attached) before
    # spending any time on cloning or the ~11GB weights download below.
    input_candidates = sorted(p for p in kaggle_input_root.glob("*") if p.is_dir())
    if not input_candidates:
        raise RuntimeError(
            f"No dataset mounted under {kaggle_input_root} - dispatch_via_kaggle() must attach "
            "the job's config/manifest dataset via KernelPushConfig.dataset_sources; this kernel "
            "was not pushed with one."
        )
    input_dir = input_candidates[0]

    git_ref_path = input_dir / "git_ref.txt"
    if not git_ref_path.is_file():
        raise RuntimeError(
            f"{git_ref_path} not found - dispatch_via_kaggle() must write the git ref this kernel "
            "should clone into the input dataset; this kernel was pushed by an out-of-date "
            "dispatch_via_kaggle() that predates docs/adr/0025-kaggle-dispatch-argv-fix.md's "
            "git-ref fix."
        )
    git_ref = git_ref_path.read_text().strip()

    _verify_cuda_available()

    if clone:
        _run(["git", "clone", "--depth", "1", "--branch", git_ref, _REPO_URL, str(repo_dir)])
        _install_missing_packages(repo_dir)

    registry_path = repo_dir / "models" / "registry.yaml"
    models_cache_root = kaggle_working_root / "models-cache"
    _run([
        sys.executable, str(repo_dir / "services" / "training" / "scripts" / "download_wan22_weights.py"),
        "--engine-id", _ENGINE_ID, "--registry", str(registry_path), "--cache-root", str(models_cache_root),
    ])

    _run([
        sys.executable, str(repo_dir / "services" / "training" / "entrypoints" / "wan22_lora_train.py"),
        "--config", str(input_dir / "config.yaml"),
        "--dataset-manifest", str(input_dir / "dataset_manifest.jsonl"),
        "--output-dir", str(kaggle_working_root / "output"),
        "--checkpoint-store-dir", str(kaggle_working_root / "checkpoints"),
        "--job-id", "kaggle-kernel-job",
        "--backend", "real",
        "--device", "auto",
        "--registry", str(registry_path),
        "--models-cache-root", str(models_cache_root),
    ])
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(f"kaggle_kernel_runner.py: step failed (exit {exc.returncode}): {exc.cmd}", file=sys.stderr)
        raise SystemExit(1) from exc
