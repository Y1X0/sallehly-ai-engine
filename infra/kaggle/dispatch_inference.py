#!/usr/bin/env python3
"""Dispatches one real Wan2.1/2.2 text-to-video inference run to a real
Kaggle free GPU kernel (P100/T4) via the real `kaggle` CLI
(`training.automation.kaggle_client.KaggleClient` - the same real
wrapper Phase 2's free-GPU training dispatch already uses).

This is a real, account-mutating action under the Kaggle account
identified by `KAGGLE_USERNAME` (authenticated via `KAGGLE_API_TOKEN` -
the `kaggle` CLI's own env var for its current access-token auth flow,
see infra/kaggle/README.md) (creates a private Kaggle dataset + kernel)
- but Kaggle's own GPU quota for this is free (no
billing, unlike RunPod). Nothing here downloads Wan weights or touches
a GPU itself - that all happens inside the dispatched kernel
(kaggle_inference_kernel_runner.py), on Kaggle's own machine.

Requires the `kaggle` package (ephemeral, not a permanent workspace
dependency - same pattern as infra/runpod/deploy_endpoint.py):

    uv run --with kaggle python infra/kaggle/dispatch_inference.py \\
        --prompt "A calm lake at sunrise, gentle ripples, warm light" \\
        --git-ref "$(git rev-parse --abbrev-ref HEAD)" \\
        --kaggle-username your-kaggle-username

Prints the real kernel_ref on success - pass it to
fetch_inference_result.py to poll and download the result.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# Reuses the real KaggleClient built for Phase 2's free-GPU training
# dispatch (services/training/src/training/automation/kaggle_client.py)
# - same account, same CLI, same real dataset-upload/kernel-push
# mechanics, only the kernel's own code differs (inference, not training).
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services" / "training" / "src"))
from training.automation.kaggle_client import (  # noqa: E402
    DatasetMetadata,
    KaggleClient,
    KaggleDatasetRef,
    KaggleKernelRef,
    KernelPushConfig,
)

_DEFAULT_MODEL_ID = "Wan-AI/Wan2.2-TI2V-5B-Diffusers"
_KERNEL_RUNNER_FILENAME = "kaggle_inference_kernel_runner.py"
# The one resolution models/wan2.2-ti2v-5b/capability_manifest.yaml
# actually declares support for - see that file's `resolutions`/
# `fps_options`. num_frames=17 (~1.06s @ 16fps) and sampling_steps=20
# are deliberately small (not this engine's real default of ~40 steps)
# to keep the very first trial run's GPU time/memory footprint down on
# a free Kaggle P100/T4 - see infra/kaggle/README.md's honest VRAM caveat.
_DEFAULT_WIDTH = 960
_DEFAULT_HEIGHT = 544
_DEFAULT_NUM_FRAMES = 17
_DEFAULT_FPS = 16
_DEFAULT_SAMPLING_STEPS = 20
_DEFAULT_GUIDANCE_SCALE = 1.0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--prompt", required=True, help="Text-to-video prompt")
    parser.add_argument("--negative-prompt", default=None)
    parser.add_argument("--model-id", default=_DEFAULT_MODEL_ID, help="Real HF Hub Wan2.1/2.2 diffusers repo id")
    parser.add_argument("--width", type=int, default=_DEFAULT_WIDTH)
    parser.add_argument("--height", type=int, default=_DEFAULT_HEIGHT)
    parser.add_argument("--num-frames", type=int, default=_DEFAULT_NUM_FRAMES)
    parser.add_argument("--fps", type=int, default=_DEFAULT_FPS)
    parser.add_argument("--sampling-steps", type=int, default=_DEFAULT_SAMPLING_STEPS)
    parser.add_argument("--guidance-scale", type=float, default=_DEFAULT_GUIDANCE_SCALE)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--git-ref", required=True,
        help="Branch/tag/commit this kernel should clone - the code_file being pushed only exists "
        "on this ref until it is merged to the repo's default branch",
    )
    parser.add_argument(
        "--kaggle-username", default=None,
        help="Kaggle account the dataset/kernel are pushed under - defaults to KAGGLE_USERNAME env var",
    )
    parser.add_argument(
        "--kernel-slug", default=None,
        help="Defaults to a timestamped slug (wan-inference-<unix-ts>) so repeated runs never collide",
    )
    parser.add_argument("--job-store-dir", default=".kaggle-inference-jobs", help="Where to write this dispatch's input files before upload")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    kaggle_username = args.kaggle_username or os.environ.get("KAGGLE_USERNAME")
    if not kaggle_username:
        print("--kaggle-username or KAGGLE_USERNAME is required.", file=sys.stderr)
        return 1

    kernel_slug = args.kernel_slug or f"wan-inference-{int(time.time())}"
    job_store = Path(args.job_store_dir) / kernel_slug
    job_store.mkdir(parents=True, exist_ok=True)

    job_input = {
        "prompt": args.prompt,
        "negative_prompt": args.negative_prompt,
        "width": args.width,
        "height": args.height,
        "num_frames": args.num_frames,
        "fps": args.fps,
        "sampling_steps": args.sampling_steps,
        "guidance_scale": args.guidance_scale,
    }
    request = {"model_id": args.model_id, "seed": args.seed, "job_input": job_input}
    (job_store / "inference_request.json").write_text(json.dumps(request, indent=2))
    (job_store / "git_ref.txt").write_text(args.git_ref)

    client = KaggleClient()

    dataset_ref = KaggleDatasetRef(owner_slug=kaggle_username, dataset_slug=f"{kernel_slug}-input")
    print(f"Uploading input dataset {dataset_ref.full_ref!r} ...")
    client.upload_dataset(
        job_store,
        DatasetMetadata(
            dataset_ref=dataset_ref,
            title=f"Wan inference input - {kernel_slug}",
            subtitle="git_ref.txt + inference_request.json for one real Kaggle GPU inference run",
        ),
        is_new=True,
    )

    kernel_ref = KaggleKernelRef(owner_slug=kaggle_username, kernel_slug=kernel_slug)
    runner_dir = Path(__file__).resolve().parent
    push_config = KernelPushConfig(
        kernel_ref=kernel_ref,
        title=f"Sallehly Wan inference - {kernel_slug}",
        code_file=_KERNEL_RUNNER_FILENAME,
        dataset_sources=(dataset_ref,),
    )
    print(f"Pushing kernel {kernel_ref.full_ref!r} ...")
    client.push_kernel(runner_dir, push_config)

    print(f"\nKernel dispatched: {kernel_ref.full_ref}")
    print("Poll it with:")
    print(f"  uv run --with kaggle python infra/kaggle/fetch_inference_result.py --kernel-ref {kernel_ref.full_ref}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
