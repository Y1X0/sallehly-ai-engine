#!/usr/bin/env python3
"""Checks a real, already-deployed RunPod Serverless endpoint's health
(`GET {endpoint_id}/health`) via `video_engine_adapter.compute.RunPodProvider.health_check()`.

Run this right after `deploy_endpoint.py` (or any time you want to
confirm the endpoint is actually reachable and has ready workers)
before pointing `apps/api` at it with `COMPUTE_PROVIDER=runpod` - a
missing/misconfigured endpoint fails clearly here instead of surfacing
as a confusing error on the first real generation request.
"""

from __future__ import annotations

import argparse
import os
import sys

from video_engine_adapter.compute import RunPodProvider
from video_engine_adapter.compute.runpod_provider import RunPodComputeError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--endpoint-id", default=None, help="Defaults to the RUNPOD_ENDPOINT_ID environment variable")
    parser.add_argument("--api-key", default=None, help="Defaults to the RUNPOD_API_KEY environment variable")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    api_key = args.api_key or os.environ.get("RUNPOD_API_KEY")
    endpoint_id = args.endpoint_id or os.environ.get("RUNPOD_ENDPOINT_ID")
    missing = [name for name, value in (("RUNPOD_API_KEY", api_key), ("RUNPOD_ENDPOINT_ID", endpoint_id)) if not value]
    if missing:
        print(f"Missing required setting(s): {', '.join(missing)} (pass --api-key/--endpoint-id or set the env vars)", file=sys.stderr)
        return 1

    provider = RunPodProvider(api_key=api_key, endpoint_id=endpoint_id)
    try:
        health = provider.health_check()
    except RunPodComputeError as exc:
        print(f"Endpoint {endpoint_id} is NOT healthy: {exc}", file=sys.stderr)
        return 1

    print(f"Endpoint {endpoint_id} responded: {health}")
    workers = health.get("workers", {})
    ready = workers.get("ready", 0)
    if ready == 0:
        print(
            "Warning: 0 ready workers - the endpoint is reachable but may need a cold start on the "
            "first real request (expect a slower first response while it downloads/loads Wan2.2 "
            "weights), or workers_min/workers_max may be misconfigured.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
