#!/usr/bin/env python3
"""Polls a Kaggle kernel (pushed by run_experiment.py --dispatch
--provider kaggle, via training.wan22.dispatch_via_kaggle) until it
reaches a terminal status, then pulls its output - including any
checkpoint files written under /kaggle/working/ by
kaggle_kernel_runner.py - to a local directory.

Wraps training.automation.KaggleClient's already-real,
already-tested poll_kernel_until_terminal()/pull_kernel_output() as a
CLI step, for use after run_experiment.py --dispatch in a CI workflow
(see .github/workflows/training-phase2-free-gpu-experiment.yml).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from training.automation import KaggleClient, KaggleKernelRef, KaggleKernelStatus


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--kernel-ref", required=True, help="owner_slug/kernel_slug")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--poll-interval-sec", type=float, default=30.0)
    parser.add_argument("--timeout-sec", type=float, default=3600.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    owner_slug, _, kernel_slug = args.kernel_ref.partition("/")
    if not kernel_slug:
        print(f"--kernel-ref must be 'owner_slug/kernel_slug', got: {args.kernel_ref!r}", file=sys.stderr)
        return 1
    kernel_ref = KaggleKernelRef(owner_slug=owner_slug, kernel_slug=kernel_slug)
    client = KaggleClient()

    print(f"Polling Kaggle kernel {kernel_ref.full_ref} until terminal (timeout={args.timeout_sec:g}s)...")
    try:
        result = client.poll_kernel_until_terminal(
            kernel_ref, poll_interval_sec=args.poll_interval_sec, timeout_sec=args.timeout_sec,
        )
    except Exception as exc:  # noqa: BLE001 - top-level CLI boundary, real failure reason goes to stderr
        print(f"Polling failed: {exc}", file=sys.stderr)
        return 1

    print(f"Kernel {kernel_ref.full_ref} finished with status={result.status.value} after {result.elapsed_sec:.1f}s")
    client.pull_kernel_output(kernel_ref, args.output_dir)
    print(f"Pulled kernel output to {args.output_dir}")

    return 0 if result.status == KaggleKernelStatus.COMPLETE else 1


if __name__ == "__main__":
    raise SystemExit(main())
