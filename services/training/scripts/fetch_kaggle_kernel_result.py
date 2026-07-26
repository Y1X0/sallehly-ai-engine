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
    parser.add_argument(
        "--validate-checkpoint", action="store_true",
        help="After pulling output, verify at least one adapter_model.safetensors exists under "
        "--output-dir and is actually loadable - fail otherwise rather than reporting success on "
        "an empty or corrupt checkpoint.",
    )
    return parser


def _validate_checkpoint(output_dir: Path) -> bool:
    """Verifies the fetched Kaggle output actually contains at least one
    loadable LoRA adapter checkpoint. Catches a run that "succeeded"
    (kernel completed, output pulled) but produced no usable checkpoint
    - e.g. it crashed before its first checkpoint_every_steps, or wrote
    a truncated/corrupt safetensors file - rather than reporting success
    on a result with nothing actually trainable to show for it."""
    adapter_files = sorted(output_dir.rglob("adapter_model.safetensors"))
    if not adapter_files:
        print(f"Checkpoint validation failed: no adapter_model.safetensors found under {output_dir}", file=sys.stderr)
        return False

    try:
        from safetensors.torch import load_file
    except ImportError as exc:
        print(f"Checkpoint validation failed: safetensors is not installed ({exc})", file=sys.stderr)
        return False

    for adapter_file in adapter_files:
        try:
            state_dict = load_file(str(adapter_file))
        except Exception as exc:  # noqa: BLE001 - any load failure means an invalid checkpoint
            print(f"Checkpoint validation failed: {adapter_file} is not loadable: {exc}", file=sys.stderr)
            return False
        if not state_dict:
            print(f"Checkpoint validation failed: {adapter_file} loaded but contains no tensors", file=sys.stderr)
            return False

    print(f"Checkpoint validation passed: {len(adapter_files)} adapter(s) under {output_dir}")
    return True


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    owner_slug, _, kernel_slug = args.kernel_ref.partition("/")
    if not kernel_slug:
        print(f"--kernel-ref must be 'owner_slug/kernel_slug', got: {args.kernel_ref!r}", file=sys.stderr)
        return 1
    kernel_ref = KaggleKernelRef(owner_slug=owner_slug, kernel_slug=kernel_slug)
    client = KaggleClient()

    print(f"Polling Kaggle kernel {kernel_ref.full_ref} until terminal (timeout={args.timeout_sec:g}s)...")
    result = None
    poll_error: Exception | None = None
    try:
        result = client.poll_kernel_until_terminal(
            kernel_ref, poll_interval_sec=args.poll_interval_sec, timeout_sec=args.timeout_sec,
        )
    except Exception as exc:  # noqa: BLE001 - polling can time out or fail transiently; still fetch below
        poll_error = exc
        print(f"Polling failed or timed out: {exc}", file=sys.stderr)

    if result is not None:
        print(f"Kernel {kernel_ref.full_ref} finished with status={result.status.value} after {result.elapsed_sec:.1f}s")

    # Always attempt to pull whatever output/logs/checkpoints exist so
    # far, even after a polling timeout - partial progress on a real GPU
    # run (or a completed run whose terminal-status poll happened to
    # fail) is valuable and must not be discarded just because polling
    # itself didn't cleanly succeed.
    try:
        client.pull_kernel_output(kernel_ref, args.output_dir)
        print(f"Pulled kernel output to {args.output_dir}")
    except Exception as exc:  # noqa: BLE001 - report but don't mask the real poll failure/status below
        print(f"Could not pull kernel output: {exc}", file=sys.stderr)

    if poll_error is not None or result.status != KaggleKernelStatus.COMPLETE:
        return 1

    if args.validate_checkpoint and not _validate_checkpoint(args.output_dir):
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
