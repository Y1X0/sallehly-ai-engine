#!/usr/bin/env python3
"""Polls a Kaggle kernel dispatched by dispatch_inference.py until it
finishes, downloads its real output, and reports exactly what
happened - a real `.mp4` (success), a real `error.json` written by
kaggle_inference_kernel_runner.py's own exception handler (a specific,
real failure reason - e.g. CUDA OOM - not a bare "Internal error"), or
neither (an infrastructure-level Kaggle failure, e.g. the kernel never
started).

Always attempts to pull whatever output exists even on a polling
timeout, same fix `services/training/scripts/fetch_kaggle_kernel_result.py`
already applies for the training path (docs/adr/0025-kaggle-dispatch-argv-fix.md)
- a kernel that finished just after the last poll should not lose its
real output to an arbitrary timeout.

    uv run --with kaggle python infra/kaggle/fetch_inference_result.py \\
        --kernel-ref your-kaggle-username/wan-inference-1234567890 \\
        --output-dir ./kaggle-inference-output
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services" / "training" / "src"))
from training.automation.errors import KaggleAutomationError  # noqa: E402
from training.automation.kaggle_client import KaggleClient, KaggleKernelRef  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--kernel-ref", required=True, help='"owner/kernel-slug", as printed by dispatch_inference.py')
    parser.add_argument("--output-dir", default="./kaggle-inference-output")
    parser.add_argument("--poll-interval-sec", type=float, default=30.0)
    parser.add_argument("--timeout-sec", type=float, default=3600.0, help="Wan2.2-TI2V-5B is ~11GB - allow time for the download+load+generate cycle, not just the denoising loop itself")
    return parser


def _parse_kernel_ref(ref: str) -> KaggleKernelRef:
    owner, _, slug = ref.partition("/")
    if not owner or not slug:
        raise ValueError(f"--kernel-ref must be 'owner/kernel-slug', got {ref!r}")
    return KaggleKernelRef(owner_slug=owner, kernel_slug=slug)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    kernel_ref = _parse_kernel_ref(args.kernel_ref)
    output_dir = Path(args.output_dir)
    client = KaggleClient()

    print(f"Polling {kernel_ref.full_ref} (timeout {args.timeout_sec:.0f}s) ...")
    try:
        result = client.poll_kernel_until_terminal(
            kernel_ref, poll_interval_sec=args.poll_interval_sec, timeout_sec=args.timeout_sec,
        )
        print(f"Kernel reached terminal status: {result.status.value} (after {result.elapsed_sec:.0f}s)")
    except KaggleAutomationError as exc:
        print(f"Polling did not reach a terminal status: {exc}", file=sys.stderr)
        print("Pulling whatever output exists anyway before giving up ...", file=sys.stderr)
        result = None

    client.pull_kernel_output(kernel_ref, output_dir)

    video_path = output_dir / "output" / "video.mp4"
    metadata_path = output_dir / "output" / "metadata.json"
    error_path = output_dir / "output" / "error.json"

    if video_path.is_file() and video_path.stat().st_size > 0:
        metadata = json.loads(metadata_path.read_text()) if metadata_path.is_file() else {}
        print(f"\nSUCCESS - real video written to {video_path} ({video_path.stat().st_size} bytes)")
        if metadata:
            print(json.dumps(metadata, indent=2))
        return 0

    if error_path.is_file():
        error = json.loads(error_path.read_text())
        print(
            f"\nFAILED - the kernel ran and reported a real error: "
            f"{error.get('error_type')}: {error.get('error_message')}",
            file=sys.stderr,
        )
        return 1

    status_note = result.status.value if result is not None else "unknown (polling did not reach a terminal status)"
    print(
        f"\nFAILED - no video.mp4 and no error.json were produced (kernel status: {status_note}). "
        f"Check the kernel's own logs at https://www.kaggle.com/code/{kernel_ref.full_ref} for the real reason "
        "(e.g. it never started, or Kaggle itself killed it before it could write output).",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
