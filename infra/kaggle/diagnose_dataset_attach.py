#!/usr/bin/env python3
"""Isolates whether the real "not valid dataset sources" warning seen
on every training-phase2-free-gpu-experiment.yml dispatch (10 real
attempts, 0s/30s/90s delays all identical) is caused by how we format
the dataset upload, or by something about the dataset/account state
that only Kaggle's own UI can show. Deliberately does NOT touch any
LoRA/training code and does NOT request a GPU - this only exercises
the dataset-upload and kernel-metadata-pull surface of the real
KaggleClient.

Two steps, run independently (see the two `--step` values below):

  1. `--step upload` - uploads one tiny real test dataset (a single
     short text file) using the exact same DatasetMetadata pattern
     training.wan22.dispatch.dispatch_via_kaggle() uses in production,
     and prints the real dataset ref + the exact metadata JSON sent.
     No kernel is pushed. A human must then confirm in the Kaggle UI
     that this dataset really exists and is visible, create an empty
     kernel there, and manually attach it via "Add Input" - a real
     UI-driven kernel push writes the dataset_sources id/slug Kaggle
     itself considers valid, which is exactly what step 2 needs to
     compare against.

  2. `--step pull-kernel-metadata --kernel-ref owner/slug` - once that
     manual kernel exists, runs `kaggle kernels pull -m` (Kaggle's own
     documented way to fetch a real kernel's generated
     kernel-metadata.json) and prints it verbatim, so it can be diffed
     by eye against what KernelPushConfig.to_kernel_metadata_dict()
     would have produced for the same dataset ref.

Usage:
    uv run --with kaggle python infra/kaggle/diagnose_dataset_attach.py \\
        --step upload --kaggle-username your-kaggle-username

    uv run --with kaggle python infra/kaggle/diagnose_dataset_attach.py \\
        --step pull-kernel-metadata --kernel-ref your-kaggle-username/some-kernel-slug
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services" / "training" / "src"))
from training.automation.kaggle_client import (  # noqa: E402
    DatasetMetadata,
    KaggleClient,
    KaggleDatasetRef,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--step", required=True, choices=("upload", "pull-kernel-metadata"))
    parser.add_argument("--kaggle-username", default=None, help="Defaults to KAGGLE_USERNAME env var")
    parser.add_argument("--dataset-slug", default=None, help="--step upload only; defaults to a timestamped slug")
    parser.add_argument("--kernel-ref", default=None, help="--step pull-kernel-metadata only: owner_slug/kernel_slug")
    parser.add_argument("--work-dir", default=".kaggle-diagnose-dataset-attach")
    return parser


def _run_upload(args: argparse.Namespace, kaggle_username: str) -> int:
    work_dir = Path(args.work_dir) / "upload"
    work_dir.mkdir(parents=True, exist_ok=True)
    (work_dir / "hello.txt").write_text(
        "Diagnostic dataset - see infra/kaggle/diagnose_dataset_attach.py.\n"
        f"Created at {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}.\n"
    )

    dataset_slug = args.dataset_slug or f"diagnose-attach-{int(time.time())}"
    dataset_ref = KaggleDatasetRef(owner_slug=kaggle_username, dataset_slug=dataset_slug)
    metadata = DatasetMetadata(
        dataset_ref=dataset_ref,
        # Deliberately the same human-readable, non-slug title format
        # production code (both dispatch_via_kaggle() and the already
        # "proven working" infra/kaggle/dispatch_inference.py) uses -
        # testing the real current behavior, not a hypothetical fix.
        # Kept under Kaggle's real 50-char title bound (found live: this
        # script's own first run used a 54-char title and got "The
        # dataset title must be between 6 and 50 characters").
        title=f"Diag attach - {dataset_slug}",
        subtitle="One tiny text file - isolates the dataset-upload/attach step from training/LoRA code entirely",
    )
    print("Uploading real test dataset with this exact metadata:")
    print(json.dumps(metadata.to_dataset_metadata_dict(), indent=2))

    client = KaggleClient()
    client.upload_dataset(work_dir, metadata, is_new=True)

    print(f"\nDataset ref: {dataset_ref.full_ref}")
    print(f"Kaggle UI:   https://www.kaggle.com/{dataset_ref.owner_slug}/datasets  (or your private datasets list)")
    print(
        "\nNext (manual, on kaggle.com - this script cannot do these):\n"
        f"  1. Confirm '{dataset_ref.full_ref}' really appears as a dataset with that exact reference.\n"
        "  2. Create a brand-new, empty Kaggle Notebook.\n"
        "  3. Use 'Add Input' in that notebook's UI to manually attach the dataset above.\n"
        "  4. Save a version (no need to actually run anything).\n"
        "  5. Note the kernel's owner/slug from its URL (kaggle.com/code/<owner>/<slug>),\n"
        "     then re-run this script with:\n"
        "       --step pull-kernel-metadata --kernel-ref <owner>/<slug>"
    )
    return 0


def _run_pull_kernel_metadata(args: argparse.Namespace) -> int:
    if not args.kernel_ref or "/" not in args.kernel_ref:
        print("--kernel-ref 'owner_slug/kernel_slug' is required for --step pull-kernel-metadata", file=sys.stderr)
        return 1

    dest_dir = Path(args.work_dir) / "pulled" / args.kernel_ref.replace("/", "_")
    dest_dir.mkdir(parents=True, exist_ok=True)
    binary = "kaggle"
    proc = subprocess.run(
        [binary, "kernels", "pull", args.kernel_ref, "-m", "-p", str(dest_dir)],
        capture_output=True, text=True,
    )
    print(proc.stdout)
    if proc.returncode != 0:
        print(f"'kaggle kernels pull -m' failed (exit {proc.returncode}):\n{proc.stderr}", file=sys.stderr)
        return 1

    metadata_path = dest_dir / "kernel-metadata.json"
    if not metadata_path.is_file():
        print(f"'kaggle kernels pull -m' succeeded but {metadata_path} was not written - contents of {dest_dir}:", file=sys.stderr)
        for p in dest_dir.iterdir():
            print(f"  {p.name}", file=sys.stderr)
        return 1

    print(f"\nReal, Kaggle-generated {metadata_path}:")
    print(metadata_path.read_text())
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    kaggle_username = args.kaggle_username or os.environ.get("KAGGLE_USERNAME")
    if args.step == "upload":
        if not kaggle_username:
            print("--kaggle-username or KAGGLE_USERNAME is required for --step upload", file=sys.stderr)
            return 1
        return _run_upload(args, kaggle_username)
    return _run_pull_kernel_metadata(args)


if __name__ == "__main__":
    raise SystemExit(main())
