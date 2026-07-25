#!/usr/bin/env python3
"""Records a human's approval of one specific paid-GPU job.

This script is only ever reached, in the .github/workflows/training-
phase3-paid-gpu-gate.yml workflow, after GitHub's own Environment
protection rules (required reviewers on the `paid-gpu-approval`
Environment) have already forced a human to click Approve on that
workflow run. By the time this script executes, the actual human
decision has already happened - this just writes it down as an
ApprovalRecord so CostGuard.authorize_paid_job() (called next, by
run_experiment.py --tier paid_gpu) can find it and let the job proceed.

There is no code path anywhere in services/training/automation that
lets a paid job run without a record like the one this script writes.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from training.automation import ApprovalRecord, FilesystemApprovalStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-store-dir", required=True, type=Path)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--approved-by", required=True, help="GitHub actor who approved the Environment gate")
    parser.add_argument("--max-cost-usd", required=True, type=float)
    args = parser.parse_args(argv)

    store = FilesystemApprovalStore(args.job_store_dir / "approvals")
    if store.get(args.job_id) is None:
        store.request(
            ApprovalRecord(job_id=args.job_id, requested_by="github-actions", max_cost_usd=args.max_cost_usd)
        )
    store.approve(
        args.job_id,
        approved_by=args.approved_by,
        reason="Approved via paid-gpu-approval GitHub Environment required reviewers",
    )
    print(f"Approved {args.job_id} for up to ${args.max_cost_usd:.2f} (approver: {args.approved_by})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
