#!/usr/bin/env python3
"""Pushes kaggle_disk_diagnostic_kernel.py as a real Kaggle kernel (same
GPU accelerator as production, so free-space numbers are representative
of what a real training dispatch would actually see), polls it to a
terminal state, then pulls and prints its real execution log verbatim.

Deliberately does NOT touch dispatch.py, kaggle_kernel_runner.py, or
download_wan22_weights.py - this is a read-only measurement kernel, no
weights are downloaded and no training runs. See
kaggle_disk_diagnostic_kernel.py's own module docstring for what it
actually measures and why (real evidence: run 31818469155 died
mid-download with "No space left on device").

Usage:
    uv run --with kaggle python infra/kaggle/dispatch_disk_diagnostic.py \\
        --kaggle-username your-kaggle-username
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services" / "training" / "src"))
from training.automation.kaggle_client import KaggleClient, KaggleKernelRef, KernelPushConfig  # noqa: E402

_KERNEL_SCRIPT_NAME = "kaggle_disk_diagnostic_kernel.py"
_GIT_REF_PLACEHOLDER = "__GIT_REF_PLACEHOLDER__"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--git-ref", default="claude/sallehly-engine-audit-vnxs4f")
    parser.add_argument("--kaggle-username", default=None, help="Defaults to KAGGLE_USERNAME env var")
    parser.add_argument("--kernel-slug", default=None, help="Defaults to a timestamped slug")
    parser.add_argument("--work-dir", default=".kaggle-disk-diagnostic")
    parser.add_argument("--poll-interval-sec", type=float, default=30.0)
    parser.add_argument("--timeout-sec", type=float, default=1800.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    kaggle_username = args.kaggle_username or os.environ.get("KAGGLE_USERNAME")
    if not kaggle_username:
        print("--kaggle-username or KAGGLE_USERNAME is required.", file=sys.stderr)
        return 1

    kernel_slug = args.kernel_slug or f"diag-disk-{int(time.time())}"
    kernel_dir = Path(args.work_dir) / "kernel"
    kernel_dir.mkdir(parents=True, exist_ok=True)

    template_path = Path(__file__).resolve().parent / _KERNEL_SCRIPT_NAME
    script_content = template_path.read_text().replace(_GIT_REF_PLACEHOLDER, args.git_ref)
    (kernel_dir / _KERNEL_SCRIPT_NAME).write_text(script_content)

    client = KaggleClient()
    kernel_ref = KaggleKernelRef(owner_slug=kaggle_username, kernel_slug=kernel_slug)
    push_config = KernelPushConfig(
        kernel_ref=kernel_ref,
        title=kernel_slug,
        code_file=_KERNEL_SCRIPT_NAME,
        dataset_sources=(),
        # Matches production's real accelerator request - Kaggle's real
        # disk allocation can differ by accelerator, so a CPU-only
        # measurement wouldn't be representative of what the real
        # training dispatch actually sees.
        enable_gpu=True,
    )
    print(f"Pushing disk-diagnostic kernel {kernel_ref.full_ref!r} (git_ref={args.git_ref!r})...")
    print(client.push_kernel(kernel_dir, push_config))

    print(f"\nPolling {kernel_ref.full_ref!r} until terminal (timeout={args.timeout_sec:g}s)...")
    result = client.poll_kernel_until_terminal(
        kernel_ref, poll_interval_sec=args.poll_interval_sec, timeout_sec=args.timeout_sec,
    )
    print(f"Kernel finished with status={result.status.value} after {result.elapsed_sec:.1f}s")
    if result.raw_status_output:
        print(f"Real status output from Kaggle:\n{result.raw_status_output}")

    dest_dir = Path(args.work_dir) / "output"
    client.pull_kernel_output(kernel_ref, dest_dir)
    log_files = sorted(dest_dir.rglob(f"{kernel_slug}.log"))
    if not log_files:
        print(f"No {kernel_slug}.log found under {dest_dir} - no execution log was captured.", file=sys.stderr)
        return 1

    for log_file in log_files:
        print(f"\n-- Full content of {log_file.name} --")
        print(log_file.read_text(errors="replace"))
    return 0 if result.status.value == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
