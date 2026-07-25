#!/usr/bin/env python3
"""CLI entrypoint for the training-factory automation layer's experiment
loop (Phase 2 free-GPU and Phase 3 paid-GPU lanes from
docs/adr/0022-training-automation-layer.md). This is the script GitHub
Actions workflows under .github/workflows/training-*.yml invoke.

By default it runs in --plan-only mode: it generates the experiment's
TrainingConfig variant (within the human-set allowed_ranges), for
PAID_GPU tier enforces CostGuard's approval+budget gate, records a
JobRecord, and prints a report. That is the entire loop this repository
currently automates for real.

--dispatch would additionally call out to KaggleClient/ModalJobLauncher
to actually push/launch a job - but doing so requires a real training
entrypoint script (the code_file a Kaggle kernel runs, or the Modal
app_entrypoint a `modal run` invokes), which this repository deliberately
does not ship yet: writing the actual Wan 2.2 LoRA training script is
Phase 9 execution, out of scope for the automation-infrastructure-only
work this script is part of. --dispatch therefore fails fast with a
clear message rather than silently doing nothing.
"""

from __future__ import annotations

import argparse
import json
import os
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
    TrainingController,
)


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
        help="Actually call out to the provider. Requires a real training entrypoint - not yet available.",
    )
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

    print(
        "No training entrypoint is wired into this script yet, so real dispatch is not available "
        "- see docs/adr/0022-training-automation-layer.md.",
        file=sys.stderr,
    )
    controller.mark_failed(job.job_id, error_message="dispatch attempted with no training entrypoint configured")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
