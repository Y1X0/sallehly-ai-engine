#!/usr/bin/env python3
"""Polls a Kaggle kernel dispatched by dispatch_diagnose_umt5.py until
it finishes, downloads its real output, and reports the result - a
real `output/metadata.json` (success, the UMT5 forward-pass stats) or
a real `output/error.json` (a specific, real failure reason). Unlike
fetch_inference_result.py, no video.mp4 is ever expected here - this
diagnostic never runs the full WanPipeline.

    uv run --with kaggle python infra/kaggle/fetch_diagnose_umt5_result.py \\
        --kernel-ref your-kaggle-username/diagnose-umt5-1234567890
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services" / "training" / "src"))
from training.automation.errors import KaggleAutomationError  # noqa: E402
from training.automation.kaggle_client import KaggleClient, KaggleKernelRef  # noqa: E402

_INITIAL_PROPAGATION_RETRIES = 4
_INITIAL_PROPAGATION_DELAY_SEC = 15.0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--kernel-ref", required=True, help='"owner/kernel-slug", as printed by dispatch_diagnose_umt5.py')
    parser.add_argument("--output-dir", default="./kaggle-diagnose-umt5-output")
    parser.add_argument("--poll-interval-sec", type=float, default=15.0)
    parser.add_argument("--timeout-sec", type=float, default=1200.0, help="This diagnostic loads only the ~6.7B text encoder, no transformer/VAE/offload staging - expected to finish in minutes, not the >1 hour a full WanPipeline run takes")
    return parser


def _parse_kernel_ref(ref: str) -> KaggleKernelRef:
    owner, _, slug = ref.partition("/")
    if not owner or not slug:
        raise ValueError(f"--kernel-ref must be 'owner/kernel-slug', got {ref!r}")
    return KaggleKernelRef(owner_slug=owner, kernel_slug=slug)


def _wait_until_kernel_is_visible(client: KaggleClient, kernel_ref: KaggleKernelRef) -> None:
    last_exc: KaggleAutomationError | None = None
    for attempt in range(1, _INITIAL_PROPAGATION_RETRIES + 1):
        try:
            client.get_kernel_status(kernel_ref)
            return
        except KaggleAutomationError as exc:
            last_exc = exc
            print(
                f"Kernel not visible yet (attempt {attempt}/{_INITIAL_PROPAGATION_RETRIES}): {exc} - "
                f"retrying in {_INITIAL_PROPAGATION_DELAY_SEC:.0f}s ...",
                file=sys.stderr,
            )
            time.sleep(_INITIAL_PROPAGATION_DELAY_SEC)
    print(
        f"Kernel still not visible after {_INITIAL_PROPAGATION_RETRIES} attempts - "
        f"proceeding anyway, last error: {last_exc}",
        file=sys.stderr,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    kernel_ref = _parse_kernel_ref(args.kernel_ref)
    output_dir = Path(args.output_dir)
    client = KaggleClient()

    _wait_until_kernel_is_visible(client, kernel_ref)

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

    try:
        client.pull_kernel_output(kernel_ref, output_dir)
    except KaggleAutomationError as exc:
        print(f"Could not download kernel output: {exc}", file=sys.stderr)

    metadata_path = output_dir / "output" / "metadata.json"
    error_path = output_dir / "output" / "error.json"

    if metadata_path.is_file():
        metadata = json.loads(metadata_path.read_text())
        print("\nSUCCESS - UMT5-only diagnostic completed:")
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
        f"\nFAILED - no metadata.json and no error.json were produced (kernel status: {status_note}). "
        f"Check the kernel's own logs at https://www.kaggle.com/code/{kernel_ref.full_ref} for the real reason.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
