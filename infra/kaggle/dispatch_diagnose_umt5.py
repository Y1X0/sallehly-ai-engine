#!/usr/bin/env python3
"""Dispatches `diagnose_umt5_kernel_runner.py` to a real Kaggle free GPU
kernel (P100/T4) - the isolated, no-`WanPipeline`, no-repo-clone UMT5
text-encoder test the user asked for after eval/reports/0019's decisive
A/B (weights confirmed real/non-meta, `enable_sequential_cpu_offload()`
confirmed not the cause, `last_hidden_state` still exactly all-zero).
Reuses the exact same real `KaggleClient` infra/kaggle/dispatch_inference.py
already uses. Needs no dataset at all unless `--prompt`/`--model-id`/
`--max-sequence-length`/`--transformers-version` are overridden from
their built-in defaults, in which case a tiny `request.json` is
uploaded the same way dispatch_inference.py uploads its own request.

    uv run --with kaggle python infra/kaggle/dispatch_diagnose_umt5.py \\
        --kaggle-username your-kaggle-username

    # To test a different transformers version pin (the user's own
    # explicit follow-up question):
    uv run --with kaggle python infra/kaggle/dispatch_diagnose_umt5.py \\
        --transformers-version 4.48.0 --kaggle-username your-kaggle-username

Prints the real kernel_ref on success - pass it to
fetch_diagnose_umt5_result.py to poll and download the result.
"""

from __future__ import annotations

import argparse
import json
import os
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

_DATASET_READY_RETRIES = 10
_DATASET_READY_DELAY_SEC = 10.0
_DATASET_READY_STATUS = "ready"
_DATASET_FAILED_STATUSES = ("failed", "deleted")
_KERNEL_RUNNER_FILENAME = "diagnose_umt5_kernel_runner.py"
_DEFAULT_MODEL_ID = "Wan-AI/Wan2.2-TI2V-5B-Diffusers"
_DEFAULT_PROMPT = "A cinematic sunset over a futuristic city, high quality"
_DEFAULT_MAX_SEQUENCE_LENGTH = 226


def _wait_until_dataset_is_ready(client: KaggleClient, dataset_ref: KaggleDatasetRef) -> None:
    for attempt in range(1, _DATASET_READY_RETRIES + 1):
        try:
            status = client.get_dataset_status(dataset_ref)
        except KaggleAutomationError as exc:
            print(f"Dataset status check failed (attempt {attempt}/{_DATASET_READY_RETRIES}): {exc}", file=sys.stderr)
            status = ""
        else:
            print(f"Dataset {dataset_ref.full_ref!r} status: {status!r} (attempt {attempt}/{_DATASET_READY_RETRIES})")
            if status == _DATASET_READY_STATUS:
                return
            if status in _DATASET_FAILED_STATUSES:
                raise RuntimeError(f"Dataset {dataset_ref.full_ref!r} reached terminal status {status!r} - cannot push a kernel referencing it")
        time.sleep(_DATASET_READY_DELAY_SEC)
    print(
        f"Dataset {dataset_ref.full_ref!r} did not reach {_DATASET_READY_STATUS!r} after "
        f"{_DATASET_READY_RETRIES} attempts - pushing the kernel anyway, it may run without input",
        file=sys.stderr,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model-id", default=_DEFAULT_MODEL_ID)
    parser.add_argument("--prompt", default=_DEFAULT_PROMPT)
    parser.add_argument("--max-sequence-length", type=int, default=_DEFAULT_MAX_SEQUENCE_LENGTH)
    parser.add_argument(
        "--transformers-version", default=None,
        help="Pin a specific transformers version inside the kernel (installed before transformers is "
        "imported) - the user's own follow-up test: does a different version change the result?",
    )
    parser.add_argument("--kaggle-username", default=None, help="Defaults to KAGGLE_USERNAME env var")
    parser.add_argument("--kernel-slug", default=None, help="Defaults to a timestamped slug")
    parser.add_argument("--job-store-dir", default=".kaggle-diagnose-umt5-jobs")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    kaggle_username = args.kaggle_username or os.environ.get("KAGGLE_USERNAME")
    if not kaggle_username:
        print("--kaggle-username or KAGGLE_USERNAME is required.", file=sys.stderr)
        return 1

    kernel_slug = args.kernel_slug or f"diagnose-umt5-{int(time.time())}"
    job_store = Path(args.job_store_dir) / kernel_slug
    job_store.mkdir(parents=True, exist_ok=True)

    request = {
        "model_id": args.model_id,
        "prompt": args.prompt,
        "max_sequence_length": args.max_sequence_length,
        "transformers_version": args.transformers_version,
    }
    (job_store / "request.json").write_text(json.dumps(request, indent=2))

    client = KaggleClient()
    dataset_ref = KaggleDatasetRef(owner_slug=kaggle_username, dataset_slug=f"{kernel_slug}-input")
    print(f"Uploading input dataset {dataset_ref.full_ref!r} ...")
    client.upload_dataset(
        job_store,
        DatasetMetadata(
            dataset_ref=dataset_ref,
            title=f"UMT5 diagnostic input - {kernel_slug}",
            subtitle="request.json for one isolated UMT5-only Kaggle GPU diagnostic run",
        ),
        is_new=True,
    )
    _wait_until_dataset_is_ready(client, dataset_ref)

    kernel_ref = KaggleKernelRef(owner_slug=kaggle_username, kernel_slug=kernel_slug)
    runner_dir = Path(__file__).resolve().parent
    push_config = KernelPushConfig(
        kernel_ref=kernel_ref,
        title=kernel_slug,
        code_file=_KERNEL_RUNNER_FILENAME,
        dataset_sources=(dataset_ref,),
        machine_shape="NvidiaTeslaT4",
    )
    print(f"Pushing kernel {kernel_ref.full_ref!r} ...")
    client.push_kernel(runner_dir, push_config)

    print(f"\nKernel dispatched: {kernel_ref.full_ref}")
    print("Poll it with:")
    print(f"  uv run --with kaggle python infra/kaggle/fetch_diagnose_umt5_result.py --kernel-ref {kernel_ref.full_ref}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
