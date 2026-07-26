#!/usr/bin/env python3
"""CLI entrypoint for the training-factory automation layer's experiment
loop (Phase 2 free-GPU and Phase 3 paid-GPU lanes from
docs/adr/0022-training-automation-layer.md). This is the script GitHub
Actions workflows under .github/workflows/training-*.yml invoke.

By default it runs in --plan-only mode: it generates the experiment's
TrainingConfig variant (within the human-set allowed_ranges), for
PAID_GPU tier enforces CostGuard's approval+budget gate, records a
JobRecord, and prints a report.

--dispatch additionally calls out to a real KaggleClient/ModalJobLauncher
to actually push/launch `services/training/entrypoints/wan22_lora_train.py`
against a pre-built dataset manifest (`--dataset-manifest`, built ahead
of time via `services/training/scripts/ingest_dataset.py`) - see
docs/adr/0024-wan22-real-training-backend.md for why this was safe to
wire in now that a real training entrypoint exists. Only provider=kaggle
and provider=modal are supported for --dispatch (the only two providers
this repository has a real automation client for); any other provider
fails fast rather than silently doing nothing.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from training import TrainingConfig
from training.automation import (
    CostGuard,
    ExperimentConfigGenerator,
    ExperimentTier,
    FilesystemApprovalStore,
    FilesystemJobStatusStore,
    FilesystemUsageLedger,
    GPUType,
    KaggleClient,
    KaggleKernelRef,
    ModalJobLauncher,
    TrainingController,
)
from training.wan22 import build_training_command_for_job, dispatch_via_kaggle, dispatch_via_modal, write_job_inputs


def load_allowed_ranges(path: Path) -> dict[str, tuple[float, float]]:
    data = json.loads(path.read_text())
    return {
        key: tuple(value)
        for key, value in data.items()
        if not key.startswith("_")
    }


def parse_overrides(pairs: list[str]) -> dict[str, float]:
    overrides: dict[str, float] = {}
    for pair in pairs:
        key, sep, value = pair.partition("=")
        if not sep:
            raise ValueError(f"--override must be KEY=VALUE, got: {pair!r}")
        overrides[key] = float(value)
    return overrides


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-config", required=True, type=Path, help="TrainingConfig YAML to start from")
    parser.add_argument("--allowed-ranges", required=True, type=Path, help="JSON file of field -> [min, max]")
    parser.add_argument("--tier", choices=[t.value for t in ExperimentTier], default="free_gpu")
    parser.add_argument("--provider", required=True, help="e.g. kaggle, modal, fal, runpod, vastai")
    parser.add_argument("--override", action="append", default=[], metavar="KEY=VALUE")
    parser.add_argument("--job-store-dir", type=Path, default=Path(".training-automation/jobs"))
    parser.add_argument("--job-id", default=None, help="Reuse a specific job_id (required to match a prior approval)")
    parser.add_argument("--estimated-cost-usd", type=float, default=0.0)
    parser.add_argument(
        "--dispatch", action="store_true",
        help="Actually call out to the provider (kaggle or modal only) and launch "
        "services/training/entrypoints/wan22_lora_train.py. Requires --dataset-manifest.",
    )
    parser.add_argument(
        "--dataset-manifest", type=Path, default=None,
        help="JSONL manifest built via services/training/scripts/ingest_dataset.py - required with --dispatch",
    )
    parser.add_argument(
        "--dispatch-runs-dir", type=Path, default=Path(".training-automation/runs"),
        help="Where the dispatched job's config.yaml/dataset_manifest.jsonl/output/checkpoints live",
    )
    parser.add_argument(
        "--entrypoint", default="services/training/entrypoints/wan22_lora_train.py",
        help="Path to the training entrypoint script a Kaggle kernel/Modal function runs. "
        "dispatch_via_kaggle writes kernel-metadata.json into this path's own directory.",
    )
    parser.add_argument("--kaggle-kernel-ref", default=None, help="'owner_slug/kernel_slug' - required for provider=kaggle")
    parser.add_argument("--modal-gpu-type", default="T4", choices=[t.value for t in GPUType])
    parser.add_argument("--modal-function-timeout-sec", type=int, default=3600)
    parser.add_argument("--modal-max-wall-clock-sec", type=int, default=4200)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    base_config = TrainingConfig.from_yaml(args.base_config)
    generator = ExperimentConfigGenerator(allowed_ranges=load_allowed_ranges(args.allowed_ranges))
    job_store = FilesystemJobStatusStore(args.job_store_dir)

    tier = ExperimentTier(args.tier)
    cost_guard = None
    if tier == ExperimentTier.PAID_GPU:
        cost_guard = CostGuard(
            approval_store=FilesystemApprovalStore(args.job_store_dir / "approvals"),
            usage_ledger=FilesystemUsageLedger(args.job_store_dir / "usage"),
            monthly_budget_usd=float(os.environ.get("TRAINING_MONTHLY_BUDGET_USD", "50")),
        )

    controller = TrainingController(job_store=job_store, config_generator=generator, cost_guard=cost_guard)

    try:
        job = controller.plan_experiment(
            base_config=base_config,
            overrides=parse_overrides(args.override),
            tier=tier,
            provider=args.provider,
            estimated_cost_usd=args.estimated_cost_usd,
            job_id=args.job_id,
        )
    except Exception as exc:  # noqa: BLE001 - top-level CLI boundary, real failure reason goes to stderr
        print(f"Could not plan experiment: {exc}", file=sys.stderr)
        return 1

    print(f"Planned job {job.job_id} (tier={job.tier.value}, provider={job.provider})")

    if not args.dispatch:
        print("--dispatch not set; stopping after planning (see module docstring for why).")
        print(controller.report(job.job_id))
        return 0

    if args.dataset_manifest is None:
        print("--dispatch requires --dataset-manifest (build one with ingest_dataset.py first)", file=sys.stderr)
        controller.mark_failed(job.job_id, error_message="dispatch attempted with no --dataset-manifest supplied")
        return 1
    if not args.dataset_manifest.is_file():
        print(f"--dataset-manifest not found: {args.dataset_manifest}", file=sys.stderr)
        controller.mark_failed(job.job_id, error_message=f"dataset manifest not found: {args.dataset_manifest}")
        return 1

    command = build_training_command_for_job(job, base_dir=str(args.dispatch_runs_dir), entrypoint=args.entrypoint)
    Path(command.dataset_manifest_path).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.dataset_manifest, command.dataset_manifest_path)
    write_job_inputs(job, command)

    try:
        if args.provider == "kaggle":
            if not args.kaggle_kernel_ref or "/" not in args.kaggle_kernel_ref:
                raise ValueError("--kaggle-kernel-ref 'owner_slug/kernel_slug' is required for provider=kaggle")
            owner_slug, _, kernel_slug = args.kaggle_kernel_ref.partition("/")
            kernel_ref = KaggleKernelRef(owner_slug=owner_slug, kernel_slug=kernel_slug)
            result = dispatch_via_kaggle(job, command, KaggleClient(), kernel_ref)
            print(f"Pushed Kaggle kernel {kernel_ref.full_ref}: {result}")
        elif args.provider == "modal":
            handle = dispatch_via_modal(
                job, command, ModalJobLauncher(),
                gpu_type=GPUType(args.modal_gpu_type),
                function_timeout_sec=args.modal_function_timeout_sec,
                max_wall_clock_sec=args.modal_max_wall_clock_sec,
            )
            print(f"Launched Modal app {handle.app_name} at {handle.started_at.isoformat()}")
        else:
            raise ValueError(
                f"--dispatch only supports provider in ('kaggle', 'modal'), got {args.provider!r} - no "
                "automation client exists in services/training/automation for this provider"
            )
    except Exception as exc:  # noqa: BLE001 - top-level CLI boundary, real failure reason goes to stderr
        print(f"Dispatch failed: {exc}", file=sys.stderr)
        controller.mark_failed(job.job_id, error_message=f"dispatch failed: {exc}")
        return 1

    controller.mark_started(job.job_id)
    print(controller.report(job.job_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
