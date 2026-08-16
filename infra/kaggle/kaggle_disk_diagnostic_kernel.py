#!/usr/bin/env python3
"""Runs entirely inside a real Kaggle kernel (same GPU accelerator as
the real training dispatch, so the numbers are representative) to
measure disk space before deciding whether Kaggle's free tier can hold
the real ~11GB Wan2.2-TI2V-5B download at all.

Real evidence this exists for: run 31818469155 (after the cwd fix let
`download_wan22_weights.py` actually start the real HF download) died
mid-transfer with "IO Error: No space left on device (os error 28)"
after only 3 of 20 files. This script does NOT download the Wan2.2
weights, does NOT touch kaggle_kernel_runner.py or
download_wan22_weights.py, and does NOT run any training - it only
measures, using the exact same real `git clone` + `pip install` steps
kaggle_kernel_runner.py performs, then computes the real byte size the
production download's own `allow_patterns` would actually pull (via
real Hugging Face Hub file metadata, no download), and reports what's
left afterward - including the effect of a real `pip cache purge` as
one concrete, measurable cleanup step.

Pushed by infra/kaggle/dispatch_disk_diagnostic.py, which fills in
__GIT_REF_PLACEHOLDER__ below with the real branch to clone before
pushing this exact file as the kernel's code_file.
"""

from __future__ import annotations

import fnmatch
import shutil
import subprocess
import sys
from pathlib import Path

_REPO_URL = "https://github.com/y1x0/sallehly-ai-engine.git"
_GIT_REF = "__GIT_REF_PLACEHOLDER__"

# Mirrors models/registry.yaml's real wan2.2-ti2v-5b download: block -
# kept as a literal copy here (not imported) since this script must run
# standalone inside the kernel before any real clone/install happens.
_HF_REPO_ID = "Wan-AI/Wan2.2-TI2V-5B-Diffusers"
_HF_REVISION = "main"
_HF_ALLOW_PATTERNS = (
    "transformer/**", "vae/**", "text_encoder/**", "tokenizer/**", "scheduler/**", "model_index.json",
)

_GB = 1024**3


def _run(args: list[str]) -> None:
    print(f"$ {' '.join(args)}", flush=True)
    subprocess.run(args, check=True)


def _report_disk_usage(label: str, path: str = "/kaggle/working") -> float:
    total, used, free = shutil.disk_usage(path)
    print(f"[{label}] {path}: total={total / _GB:.2f}GB used={used / _GB:.2f}GB free={free / _GB:.2f}GB", flush=True)
    return free / _GB


def _dir_size_gb(path: Path) -> float:
    if not path.is_dir():
        return 0.0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / _GB


def main() -> int:
    _report_disk_usage("before anything")

    repo_dir = Path("/kaggle/working/repo")
    _run(["git", "clone", "--depth", "1", "--branch", _GIT_REF, _REPO_URL, str(repo_dir)])
    print(f"repo size after clone: {_dir_size_gb(repo_dir):.3f}GB", flush=True)
    _report_disk_usage("after git clone")

    _run([
        sys.executable, "-m", "pip", "install", "--quiet", "--no-deps",
        "-e", str(repo_dir / "packages" / "video-engine-sdk"),
        "-e", str(repo_dir / "services" / "training"),
    ])
    _run([sys.executable, "-m", "pip", "install", "--quiet", "transformers==4.48.0"])
    pip_cache_dir = Path.home() / ".cache" / "pip"
    print(f"pip cache size after installs: {_dir_size_gb(pip_cache_dir):.3f}GB", flush=True)
    hf_cache_dir = Path.home() / ".cache" / "huggingface"
    print(f"pre-existing huggingface cache size: {_dir_size_gb(hf_cache_dir):.3f}GB", flush=True)
    free_after_install_gb = _report_disk_usage("after pip installs")

    print("\n$ pip cache purge  (real, measurable cleanup - not touching any production code)", flush=True)
    _run([sys.executable, "-m", "pip", "cache", "purge"])
    free_after_cleanup_gb = _report_disk_usage("after pip cache purge")

    print("\nComputing the REAL Wan2.2-TI2V-5B download size via HF Hub file metadata (no download)...", flush=True)
    try:
        from huggingface_hub import HfApi
    except ImportError:
        _run([sys.executable, "-m", "pip", "install", "--quiet", "huggingface_hub"])
        from huggingface_hub import HfApi

    api = HfApi()
    info = api.model_info(_HF_REPO_ID, revision=_HF_REVISION, files_metadata=True)
    matched = [
        f for f in info.siblings
        if f.size is not None and any(fnmatch.fnmatch(f.rfilename, pattern) for pattern in _HF_ALLOW_PATTERNS)
    ]
    total_download_gb = sum(f.size for f in matched) / _GB
    print(f"Matched {len(matched)} real files, real total download size: {total_download_gb:.3f}GB", flush=True)
    for f in sorted(matched, key=lambda x: -x.size)[:10]:
        print(f"  {f.rfilename}: {f.size / (1024**2):.1f}MB", flush=True)

    print(f"\nFree space after clone+install: {free_after_install_gb:.2f}GB")
    print(f"Free space after pip cache purge: {free_after_cleanup_gb:.2f}GB")
    print(f"Real download needs (single copy): {total_download_gb:.2f}GB")
    print(f"snapshot_download's real worst case (temp + final copy, no symlink dedup): ~{total_download_gb * 2:.2f}GB")

    if free_after_cleanup_gb < total_download_gb:
        print("\n=> VERDICT: NOT enough free space even for a single copy of the weights, even after cleanup.")
    elif free_after_cleanup_gb < total_download_gb * 1.5:
        print("\n=> VERDICT: Marginal - enough for one copy but likely not enough headroom for snapshot_download's temp/cache overhead.")
    else:
        print("\n=> VERDICT: Should be enough space, even accounting for temporary download overhead.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
