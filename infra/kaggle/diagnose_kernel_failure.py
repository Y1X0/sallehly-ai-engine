#!/usr/bin/env python3
"""Investigates a real Kaggle kernel that reached status=error, without
launching any new dispatch/training run - it only queries the Kaggle API
about a kernel that already finished. Built after two real dispatches
(runs 31797445523 and 31798057770) both pushed cleanly (the dataset-
attach bug is fixed and confirmed) but the kernel itself then errored
after ~31s both times, with `kaggle kernels status`'s own
`Failure message` field empty - meaning the standard status check gives
no reason. Deliberately does NOT touch dispatch.py, kaggle_kernel_runner.py,
or any other training/LoRA code, and does NOT dispatch anything new.

Collects every piece of information the real Kaggle API exposes for an
existing kernel and prints it all to this run's own job log (no separate
artifact download needed):

  1. `kaggle kernels status <ref>` - the raw status line Kaggle returns,
     including any `Failure message:` if present (see
     KaggleClient._get_kernel_status_raw's own docstring).
  2. `kaggle kernels output <ref> -p <dir>` - pulls every real output
     file Kaggle has for the kernel's last session, including a
     `<kernel_slug>.log` file if Kaggle captured any execution log at
     all (this is the *same* data `kaggle kernels logs <ref>` exposes -
     both read `ApiListKernelSessionOutputRequest`'s `response.log`).
     Every pulled file's name + size is printed, and the full content of
     the `.log` file (if one was written) is printed verbatim.

Whether the pulled log contains any of kaggle_kernel_runner.py's own
early print statements (e.g. "$ git clone ...", or the
"torch.cuda.is_available() is False..." message from its step-0 GPU
check) is the concrete signal for whether the failure happened before
or after our runner code actually started running.

Usage:
    uv run --with kaggle python infra/kaggle/diagnose_kernel_failure.py \\
        --kernel-ref your-kaggle-username/wan22-ci-smoke-31797445523 \\
        --kernel-ref your-kaggle-username/wan22-ci-smoke-31798057770
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services" / "training" / "src"))
from training.automation import KaggleAutomationError, KaggleClient, KaggleKernelRef  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--kernel-ref", required=True, action="append",
        help="owner_slug/kernel_slug of an already-finished kernel to investigate. Repeatable.",
    )
    parser.add_argument("--work-dir", default=".kaggle-diagnose-kernel-failure")
    return parser


def _investigate_one(client: KaggleClient, kernel_ref_str: str, work_dir: Path) -> None:
    print(f"\n{'=' * 70}\nInvestigating {kernel_ref_str}\n{'=' * 70}")
    owner_slug, _, kernel_slug = kernel_ref_str.partition("/")
    if not kernel_slug:
        print(f"  --kernel-ref must be 'owner_slug/kernel_slug', got: {kernel_ref_str!r}", file=sys.stderr)
        return
    kernel_ref = KaggleKernelRef(owner_slug=owner_slug, kernel_slug=kernel_slug)

    print("\n-- kaggle kernels status --")
    try:
        status, raw_status_output = client._get_kernel_status_raw(kernel_ref)  # noqa: SLF001 - deliberate direct use for this diagnostic
        print(f"Parsed status: {status.value}")
        print(f"Raw output:\n{raw_status_output}")
    except KaggleAutomationError as exc:
        print(f"kernels status failed: {exc}")

    print("\n-- kaggle kernels output (pulls every real output/log file Kaggle has) --")
    dest_dir = work_dir / kernel_ref_str.replace("/", "_")
    try:
        client.pull_kernel_output(kernel_ref, dest_dir)
    except KaggleAutomationError as exc:
        print(f"kernels output failed: {exc}")
        return

    pulled_files = sorted(dest_dir.rglob("*"))
    pulled_files = [p for p in pulled_files if p.is_file()]
    if not pulled_files:
        print(f"No output files at all were pulled for {kernel_ref_str} - Kaggle has nothing recorded for this session.")
        return

    print(f"Pulled {len(pulled_files)} file(s):")
    for f in pulled_files:
        print(f"  {f.relative_to(dest_dir)}  ({f.stat().st_size} bytes)")

    log_files = [f for f in pulled_files if f.name == f"{kernel_slug}.log"]
    if not log_files:
        print(f"\nNo {kernel_slug}.log was written - Kaggle's `response.log` was empty for this session.")
    for log_file in log_files:
        print(f"\n-- Full content of {log_file.name} --")
        content = log_file.read_text(errors="replace")
        print(content if content.strip() else "(log file exists but is empty)")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    client = KaggleClient()
    work_dir = Path(args.work_dir)
    for kernel_ref_str in args.kernel_ref:
        _investigate_one(client, kernel_ref_str, work_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
