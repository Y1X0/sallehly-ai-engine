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
  1. Shallow-clones this repo (public, no auth needed for read access)
     at the git ref recorded in `git_ref.txt` (written by
     `dispatch_via_kaggle()` into the same mounted dataset as
     config.yaml/dataset_manifest.jsonl - a plain `git clone` with no
     `--branch` would silently pull whatever the repo's *default*
     branch happens to be, which will not contain this code until this
     work is merged there) into `/kaggle/working/repo`, and installs
     `video-engine-sdk` + `training[gpu-training]` from it in editable
     mode - real network access, requires the kernel's `enable_internet`
     setting to be True (it is, by default - see `KernelPushConfig`).
  2. Runs the repo's own `download_wan22_weights.py` for real, fresh,
     inside this run's container. `HF_TOKEN`, if the target repo needs
     one, must be attached to this kernel as a Kaggle Secret exposed as
     an environment variable of the same name (Kaggle Settings ->
     Secrets on the kernel) - never hardcoded here.
  3. Reads `config.yaml`/`dataset_manifest.jsonl` from the Kaggle
     dataset `dispatch_via_kaggle()` uploads and mounts read-only under
     `/kaggle/input/<slug>/` - the real substitute for CLI arguments.
  4. Runs the cloned repo's own `wan22_lora_train.py --backend real`
     against those paths, writing output/checkpoints under
     `/kaggle/working/` - the directory `kaggle kernels output` (and
     this repo's `fetch_kaggle_kernel_result.py`) downloads after the
     kernel finishes.

Pushed by `dispatch_via_kaggle()` alongside `wan22_lora_train.py`, but
does not import it - everything below runs the cloned copy as a real
subprocess, so this script itself has zero dependency on `training`
being importable in whatever environment Kaggle happens to run it in.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO_URL = "https://github.com/y1x0/sallehly-ai-engine.git"
_ENGINE_ID = "wan2.2-ti2v-5b"


def _run(args: list[str]) -> None:
    print(f"$ {' '.join(args)}", flush=True)
    subprocess.run(args, check=True)


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

    if clone:
        _run(["git", "clone", "--depth", "1", "--branch", git_ref, _REPO_URL, str(repo_dir)])
        _run([
            sys.executable, "-m", "pip", "install", "--quiet",
            "-e", str(repo_dir / "packages" / "video-engine-sdk"),
            "-e", f"{repo_dir / 'services' / 'training'}[gpu-training]",
        ])

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
