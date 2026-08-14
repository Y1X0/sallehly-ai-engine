#!/usr/bin/env python3
"""Modal wrapper for wan22_lora_train.py - the Modal-provider equivalent
of kaggle_kernel_runner.py.

Built after real evidence from this repo's own Kaggle dispatch attempts:
Kaggle's free-tier kernel disk (~19.5GB total, measured live via
infra/kaggle/kaggle_disk_diagnostic_kernel.py) cannot hold Wan2.2-TI2V-5B's
real weight footprint (~31.85GB, computed from real Hugging Face Hub file
metadata - models/registry.yaml's own "~11GB" comment was a stale
estimate). Modal's persistent Volumes remove that ceiling entirely, and
unlike a Kaggle kernel's clean-container-per-run model, a Volume means
the real ~32GB weight download only ever has to happen once.

This file is a THIN wrapper, not a training reimplementation. It does
not touch, reimplement, or duplicate any real training logic - it only:
  1. Prepares the environment - declaratively, via the `image` built
     below (Modal bakes a container image ahead of time rather than
     installing packages at runtime the way kaggle_kernel_runner.py
     has to; the exact same gpu-training extra's real dependency pins
     are mirrored here for consistency, not reinvented).
  2. Finds-or-downloads the real Wan2.2 TI2V-5B weights onto the
     Volume, skipping the real ~31.85GB transfer entirely if a prior
     run already cached them there.
  3. Treats `config`/`dataset_manifest` as paths already staged on the
     Volume (see the real, unsolved gap documented below).
  4. Invokes the existing, completely unmodified
     services/training/entrypoints/wan22_lora_train.py --backend real
     as a real subprocess - the exact same script and argv shape
     kaggle_kernel_runner.py already uses for the same purpose.
  5. Commits the Volume so checkpoints/eval outputs durably persist
     across runs (Modal Volumes require an explicit commit() to
     guarantee durability of writes).

Structured so the actual sequencing logic (`_run_training`) is a
plain, fully argument-injectable function with zero Modal-specific
code - directly unit-testable (see tests/test_modal_wan22_train_app.py)
the same way tests/test_training_kaggle_kernel_runner.py tests
kaggle_kernel_runner.main(), without any real Modal account, GPU, or
network access. `train_wan22_lora` below is a thin `@app.function`
wrapper around that plain function, matching how Modal itself expects
the real remote-execution entrypoint to look.

*** Real, honest limitation this file does NOT solve (deliberately out
of scope - would require changing training.wan22.command.TrainingCommand/
dispatch_via_modal(), both explicitly untouched for this change) ***
`TrainingCommand.to_modal_extra_args()` passes `--config`/
`--dataset-manifest` as bare path STRINGS - the same contract used for
a local subprocess or a Kaggle kernel, where the referenced files
already exist on that machine's own filesystem by the time the command
runs. Modal's CLI does not auto-upload a local file referenced by a
plain string argument; it passes the string through unchanged. So
`config`/`dataset_manifest` here must already point at real files on
THIS app's Volume by the time `train_wan22_lora` runs - staging them
there is a real, standard Modal CLI step
(`modal volume put <volume-name> <local-config.yaml> runs/<job_id>/config.yaml`),
not something this file or dispatch_via_modal() currently automates.

Confirmed against a real, locally-installed `modal` package (1.5.4,
via `uv run --with modal ...` - see this file's own test for exactly
what was verified): `modal.App`, `modal.Volume.from_name`,
`modal.Image.debian_slim().pip_install().add_local_dir()`, and
`@app.function(image=..., gpu=..., volumes=..., timeout=...)` all
construct correctly with zero errors and require no Modal account/
token at import/construction time. What has NOT been verified: an
actual `modal run`/`modal deploy` against a real Modal account - no
GPU has been requested and no training has run. That is a separate,
later, explicitly-approved step.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Callable

import modal

_APP_NAME = "wan22-lora-train"
_VOLUME_NAME = "wan22-training-data"
_VOLUME_MOUNT_PATH = "/vol"
_ENGINE_ID = "wan2.2-ti2v-5b"
_REPO_MOUNT_PATH = "/repo"
# A10G, not A100 - explicit choice for this first probe: enough VRAM
# headroom over the config's own (unverified) 16GB floor
# (services/training/configs/wan22_finetune.yaml) without paying for
# capacity a 50-100 step smoke test doesn't need.
_GPU_TYPE = "A10G"
# Generous enough for a real ~31.85GB weight download (once) plus a
# short 50-100 step probe, without being large enough to mask a truly
# hung job - enforced by Modal's own real per-function timeout, not a
# separate polling mechanism the way ModalJobLauncher.enforce_wall_clock_ceiling
# is for the CLI-launch path.
_FUNCTION_TIMEOUT_SEC = 3600

_REPO_ROOT = Path(__file__).resolve().parents[3]

app = modal.App(_APP_NAME)
volume = modal.Volume.from_name(_VOLUME_NAME, create_if_missing=True)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        # Mirrors services/training/pyproject.toml's real gpu-training
        # extra pins exactly - not reinvented, just declared ahead of
        # time the way a Modal image requires, instead of installed at
        # runtime the way kaggle_kernel_runner.py has to.
        "torch>=2.3",
        "diffusers>=0.31",
        "transformers==4.48.0",
        "accelerate>=0.33",
        "peft>=0.12",
        "safetensors>=0.4",
        "huggingface_hub>=0.24",
        "imageio>=2.34",
        "imageio-ffmpeg>=0.5",
        "pyyaml>=6.0",
    )
    .add_local_dir(str(_REPO_ROOT), remote_path=_REPO_MOUNT_PATH)
)


def _run(args: list[str], *, cwd: Path | None = None) -> None:
    print(f"$ {' '.join(args)}", flush=True)
    subprocess.run(args, check=True, cwd=cwd)


def _weights_already_cached(cache_root: Path) -> bool:
    """True once a prior run already wrote real weight files under
    `cache_root` - checked so a Volume-cached run never re-pays the
    real ~31.85GB transfer twice. Mirrors the real, on-disk layout
    `download_wan22_weights.py`/`HuggingFaceWeightsDownloader` actually
    write (a `<engine_id>/` subfolder under `--cache-root` containing
    the downloaded `*.safetensors` shards)."""
    engine_dir = cache_root / _ENGINE_ID
    return engine_dir.is_dir() and any(engine_dir.rglob("*.safetensors"))


def _run_training(
    *,
    config_path: str,
    dataset_manifest_path: str,
    output_dir: str,
    checkpoint_store_dir: str,
    job_id: str,
    repo_root: Path,
    models_cache_root: Path,
    run: Callable[..., None] = _run,
) -> int:
    """The real sequence - framework-agnostic, zero Modal-specific
    code, fully testable with an injected `run` callable. Mirrors
    kaggle_kernel_runner.py's own main() step-for-step: find-or-download
    weights, then invoke the existing wan22_lora_train.py --backend
    real entrypoint unmodified."""
    registry_path = repo_root / "models" / "registry.yaml"

    if _weights_already_cached(models_cache_root):
        print(f"Wan2.2 weights already cached at {models_cache_root} - skipping the real download.")
    else:
        run([
            sys.executable, str(repo_root / "services" / "training" / "scripts" / "download_wan22_weights.py"),
            "--engine-id", _ENGINE_ID, "--registry", str(registry_path), "--cache-root", str(models_cache_root),
        ], cwd=repo_root)

    run([
        sys.executable, str(repo_root / "services" / "training" / "entrypoints" / "wan22_lora_train.py"),
        "--config", config_path,
        "--dataset-manifest", dataset_manifest_path,
        "--output-dir", output_dir,
        "--checkpoint-store-dir", checkpoint_store_dir,
        "--job-id", job_id,
        "--backend", "real",
        "--device", "auto",
        "--registry", str(registry_path),
        "--models-cache-root", str(models_cache_root),
    ], cwd=repo_root)
    return 0


@app.function(
    image=image,
    gpu=_GPU_TYPE,
    volumes={_VOLUME_MOUNT_PATH: volume},
    timeout=_FUNCTION_TIMEOUT_SEC,
)
def train_wan22_lora(
    config: str,
    dataset_manifest: str,
    output_dir: str,
    checkpoint_store_dir: str,
    job_id: str,
) -> int:
    """Real Modal entrypoint - matches `function_name="train_wan22_lora"`
    (training.wan22.dispatch.dispatch_via_modal()'s own default) and the
    exact flag names `TrainingCommand.to_modal_extra_args()` already
    produces (`--config`, `--dataset-manifest`, `--output-dir`,
    `--checkpoint-store-dir`, `--job-id` - Modal's CLI dash-to-underscore
    normalizes these onto this function's own parameter names)."""
    exit_code = _run_training(
        config_path=config,
        dataset_manifest_path=dataset_manifest,
        output_dir=output_dir,
        checkpoint_store_dir=checkpoint_store_dir,
        job_id=job_id,
        repo_root=Path(_REPO_MOUNT_PATH),
        models_cache_root=Path(_VOLUME_MOUNT_PATH) / "models-cache",
    )
    volume.commit()
    return exit_code
