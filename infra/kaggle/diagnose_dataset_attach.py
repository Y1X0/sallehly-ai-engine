#!/usr/bin/env python3
"""Isolates whether the real "not valid dataset sources" warning seen
on every training-phase2-free-gpu-experiment.yml dispatch (10 real
attempts, 0s/30s/90s delays all identical) is caused by how we format
the dataset upload, or by something about the dataset/account state
that only Kaggle's own UI can show. Deliberately does NOT touch any
LoRA/training code and does NOT request a GPU - this only exercises
the dataset-upload and kernel-metadata-pull surface of the real
KaggleClient.

Three steps, run independently (see the `--step` values below). `upload`
+ `push-kernel` are both fully automated (no browser, no GPU) and are the
preferred path - `pull-kernel-metadata` only matters if a human separately
does the manual UI attach described under step 1.

  1. `--step upload` - uploads one tiny real test dataset (a single
     short text file) using the exact same DatasetMetadata pattern
     training.wan22.dispatch.dispatch_via_kaggle() uses in production,
     and prints the real dataset ref + the exact metadata JSON sent.
     No kernel is pushed.

  2. `--step push-kernel --dataset-ref owner/dataset-slug` - fully
     automated, no browser needed. First probes real dataset readiness
     by retrying `kaggle datasets download` (NOT `datasets status` -
     that endpoint 403'd persistently across every real production
     attempt, so it was never a trustworthy readiness signal to begin
     with). Once the dataset is confirmed downloadable (or the probe
     window runs out), pushes a trivial `enable_gpu=False` kernel via
     the exact same KernelPushConfig/KaggleClient.push_kernel() code
     path production training dispatch uses, with this dataset attached.
     The "not valid dataset sources" warning (if it happens) appears
     directly in `kernels push`'s own stdout - no kernel run/GPU wait
     needed to see it. This isolates: does a *provably ready* dataset,
     pushed with production-identical code, still trigger the warning?
     If yes -> not a client-side format/timing bug, points at a
     Kaggle-side dataset/account-state issue. If no -> the real cause
     was `datasets status` giving a false readiness signal all along.

  3. `--step pull-kernel-metadata --kernel-ref owner/slug` - only
     needed if a human manually attaches the uploaded dataset to a
     kernel via Kaggle's UI ("Add Input") instead of using step 2.
     Runs `kaggle kernels pull -m` (Kaggle's own documented way to
     fetch a real kernel's generated kernel-metadata.json) and prints
     it verbatim, to diff by eye against
     KernelPushConfig.to_kernel_metadata_dict()'s output.

Usage:
    uv run --with kaggle python infra/kaggle/diagnose_dataset_attach.py \\
        --step upload --kaggle-username your-kaggle-username

    uv run --with kaggle python infra/kaggle/diagnose_dataset_attach.py \\
        --step push-kernel --dataset-ref your-kaggle-username/diagnose-attach-1234

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
from training.automation.errors import KaggleAutomationError  # noqa: E402
from training.automation.kaggle_client import (  # noqa: E402
    DatasetMetadata,
    KaggleClient,
    KaggleDatasetRef,
    KaggleKernelRef,
    KernelPushConfig,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--step", required=True, choices=("upload", "push-kernel", "pull-kernel-metadata"))
    parser.add_argument("--kaggle-username", default=None, help="Defaults to KAGGLE_USERNAME env var")
    parser.add_argument("--dataset-slug", default=None, help="--step upload only; defaults to a timestamped slug")
    parser.add_argument("--dataset-ref", default=None, help="--step push-kernel only: owner_slug/dataset_slug to attach")
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
        # Kept within Kaggle's real 20-80 char subtitle bound too (found
        # live on this same run: the previous, longer subtitle got
        # "Subtitle length must be between 20 and 80 characters").
        subtitle="One tiny text file - isolates dataset attach from training code",
    )
    print("Uploading real test dataset with this exact metadata:")
    print(json.dumps(metadata.to_dataset_metadata_dict(), indent=2))

    client = KaggleClient()
    client.upload_dataset(work_dir, metadata, is_new=True)

    print(f"\nDataset ref: {dataset_ref.full_ref}")
    print(
        "\nNext (fully automated, no browser needed):\n"
        f"  uv run --with kaggle python infra/kaggle/diagnose_dataset_attach.py \\\n"
        f"      --step push-kernel --dataset-ref {dataset_ref.full_ref}"
    )
    return 0


def _run_push_kernel(args: argparse.Namespace, kaggle_username: str) -> int:
    if not args.dataset_ref or "/" not in args.dataset_ref:
        print("--dataset-ref 'owner_slug/dataset_slug' is required for --step push-kernel", file=sys.stderr)
        return 1
    owner_slug, dataset_slug = args.dataset_ref.split("/", 1)
    dataset_ref = KaggleDatasetRef(owner_slug=owner_slug, dataset_slug=dataset_slug)
    client = KaggleClient()

    print(
        f"Probing real readiness of {dataset_ref.full_ref} via 'kaggle datasets download' "
        "(not 'datasets status' - that endpoint 403'd persistently across every real "
        "production attempt, so it was never a trustworthy readiness signal)..."
    )
    probe_dir = Path(args.work_dir) / "readiness-probe"
    ready = False
    for attempt in range(1, 13):
        try:
            client.download_dataset(dataset_ref, probe_dir)
        except KaggleAutomationError as exc:
            print(f"  attempt {attempt}/12: not downloadable yet ({exc})")
            time.sleep(10)
        else:
            ready = True
            print(f"  attempt {attempt}/12: download succeeded - dataset is genuinely readable server-side.")
            break
    if not ready:
        print(
            "Dataset never became downloadable within the 120s probe window - "
            "pushing the kernel anyway to see the real warning.",
            file=sys.stderr,
        )

    kernel_slug = f"diag-push-{int(time.time())}"
    kernel_dir = Path(args.work_dir) / "kernel"
    kernel_dir.mkdir(parents=True, exist_ok=True)
    (kernel_dir / "script.py").write_text("print('diagnostic kernel - no GPU, no training/LoRA code')\n")

    config = KernelPushConfig(
        kernel_ref=KaggleKernelRef(owner_slug=kaggle_username, kernel_slug=kernel_slug),
        # Same title==kernel_slug pattern the real kernel-slug-mismatch fix
        # established for production dispatch.
        title=kernel_slug,
        code_file="script.py",
        dataset_sources=(dataset_ref,),
        enable_gpu=False,
    )
    print(f"\nPushing minimal no-GPU kernel {config.kernel_ref.full_ref} with dataset_sources=[{dataset_ref.full_ref}]...")
    output = client.push_kernel(kernel_dir, config)
    print(output)

    lowered = output.lower()
    if "not valid dataset sources" in lowered or "could not be added" in lowered:
        print(
            "\n=> RESULT: the warning was reproduced even with a confirmed-ready dataset and "
            "production-identical push code. This points at a Kaggle-side dataset/account-state "
            "issue, not a client-side metadata format or timing bug."
        )
    else:
        print(
            "\n=> RESULT: no dataset-attach warning this time. This suggests the earlier failures "
            "really were a readiness race that 'datasets status' failed to detect (it was "
            "403'ing), now correctly handled by probing via 'datasets download' instead."
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
    if args.step == "push-kernel":
        if not kaggle_username:
            print("--kaggle-username or KAGGLE_USERNAME is required for --step push-kernel", file=sys.stderr)
            return 1
        return _run_push_kernel(args, kaggle_username)
    return _run_pull_kernel_metadata(args)


if __name__ == "__main__":
    raise SystemExit(main())
