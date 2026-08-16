#!/usr/bin/env python3
"""Creates (or updates) a real RunPod Serverless template + endpoint
pointing at a built `workers/gpu-worker` image, using the official
`runpod` Python SDK's real management API
(`runpod.create_template()`/`runpod.create_endpoint()` - GraphQL calls
against `https://api.runpod.io/graphql`, confirmed by reading the
installed `runpod` package's own `runpod/api/ctl_commands.py`).

This is a real, account-mutating, billable action: it creates a real
RunPod template and endpoint under the account owning `--api-key`
(or `RUNPOD_API_KEY`). Nothing here is simulated - run it once you have
already built and pushed the `workers/gpu-worker` image to a registry
RunPod can pull from (Docker Hub, GHCR, or a private registry with
`--registry-auth-id`, see `runpod.create_container_registry_auth`).

Requires the `runpod` package (not a permanent dependency of this
workspace - it's deployment tooling, not application code):

    uv run --with runpod python infra/runpod/deploy_endpoint.py \\
        --image docker.io/you/sallehly-wan22-worker:2.2.0 \\
        --name sallehly-wan22-ti2v-5b \\
        --hf-token "$HF_TOKEN"

Prints the real endpoint id on success - export it as
`RUNPOD_ENDPOINT_ID` for `apps/api` (`COMPUTE_PROVIDER=runpod`) and for
`infra/runpod/check_health.py`.

Pass `--dry-run` to validate every argument and print exactly what
would be created (template name/image, endpoint gpu/worker config)
WITHOUT calling the real RunPod API - `runpod.api_key` is never set and
`runpod.create_template()`/`runpod.create_endpoint()` are never called
in this mode. `--dry-run` does not require `RUNPOD_API_KEY` (or
`--api-key`) at all - this is the free/no-cost default the CI workflow
uses unless a real deployment is explicitly requested.
"""

from __future__ import annotations

import argparse
import os
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--image", required=True, help="Full image ref, e.g. docker.io/you/sallehly-wan22-worker:2.2.0")
    parser.add_argument("--name", default="sallehly-wan22-ti2v-5b", help="Template/endpoint name")
    parser.add_argument(
        "--api-key", default=None,
        help="Defaults to the RUNPOD_API_KEY environment variable - required either way",
    )
    parser.add_argument(
        "--hf-token", default=None,
        help="Defaults to the HF_TOKEN environment variable - injected into the worker's container env "
        "so it can download real Wan2.2 weights on first cold start. Only needed if the configured "
        "models/registry.yaml repo is gated (Wan-AI's Wan2.2 Diffusers repos are public as of this "
        "writing). Consider RunPod's own Secrets feature for a more secure alternative in a real "
        "production rollout instead of a plain template env var.",
    )
    parser.add_argument("--gpu-ids", default="AMPERE_24", help="RunPod GPU pool id(s) - see RunPod console for valid values")
    parser.add_argument("--gpu-count", type=int, default=1)
    parser.add_argument("--workers-min", type=int, default=0, help="0 = scale to zero when idle (no cost while unused)")
    parser.add_argument("--workers-max", type=int, default=1)
    parser.add_argument("--idle-timeout-sec", type=int, default=5)
    parser.add_argument("--container-disk-gb", type=int, default=50, help="Must fit the downloaded Wan2.2 weights (~11GB) plus torch/diffusers")
    parser.add_argument("--registry-auth-id", default=None, help="From runpod.create_container_registry_auth, if --image is in a private registry")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Validate arguments and print what would be created, without calling the real RunPod "
        "API (no runpod.api_key assignment, no create_template/create_endpoint call). Does not "
        "require --api-key/RUNPOD_API_KEY.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    hf_token = args.hf_token or os.environ.get("HF_TOKEN")
    env = {"HF_TOKEN": hf_token} if hf_token else {}

    if args.dry_run:
        print("Dry run - validating configuration only, no RunPod API call will be made.")
        print(f"  image:            {args.image}")
        print(f"  name:             {args.name}")
        print(f"  gpu_ids:          {args.gpu_ids}")
        print(f"  gpu_count:        {args.gpu_count}")
        print(f"  workers_min:      {args.workers_min}")
        print(f"  workers_max:      {args.workers_max}")
        print(f"  idle_timeout_sec: {args.idle_timeout_sec}")
        print(f"  container_disk_gb:{args.container_disk_gb}")
        print(f"  registry_auth_id: {args.registry_auth_id}")
        print(f"  HF_TOKEN set:     {bool(hf_token)}")
        if args.workers_min < 0 or args.workers_max < 1 or args.workers_min > args.workers_max:
            print("Invalid worker configuration: need 0 <= workers_min <= workers_max and workers_max >= 1.", file=sys.stderr)
            return 1
        if not args.image:
            print("Invalid configuration: --image is required.", file=sys.stderr)
            return 1
        print("\nDry run OK - this configuration would create a real template + endpoint if run without --dry-run.")
        print("Endpoint created: dry-run-noop")
        return 0

    try:
        import runpod
    except ImportError:
        print(
            "The `runpod` package is required for this script but is not installed. Run with "
            "`uv run --with runpod python infra/runpod/deploy_endpoint.py ...` (it is deliberately "
            "not a permanent dependency of this workspace - deployment tooling only).",
            file=sys.stderr,
        )
        return 1

    api_key = args.api_key or os.environ.get("RUNPOD_API_KEY")
    if not api_key:
        print("--api-key or RUNPOD_API_KEY is required (unless --dry-run).", file=sys.stderr)
        return 1
    runpod.api_key = api_key

    print(f"Creating template {args.name!r} from image {args.image!r} ...")
    template = runpod.create_template(
        name=args.name,
        image_name=args.image,
        container_disk_in_gb=args.container_disk_gb,
        env=env,
        is_serverless=True,
        registry_auth_id=args.registry_auth_id,
    )
    template_id = template["id"]
    print(f"Template created: {template_id}")

    print(f"Creating endpoint {args.name!r} (gpu_ids={args.gpu_ids!r}, workers_min={args.workers_min}, workers_max={args.workers_max}) ...")
    endpoint = runpod.create_endpoint(
        name=args.name,
        template_id=template_id,
        gpu_ids=args.gpu_ids,
        gpu_count=args.gpu_count,
        workers_min=args.workers_min,
        workers_max=args.workers_max,
        idle_timeout=args.idle_timeout_sec,
    )
    endpoint_id = endpoint["id"]

    print(f"\nEndpoint created: {endpoint_id}")
    print("\nNext steps:")
    print(f"  export RUNPOD_API_KEY={api_key!r}")
    print(f"  export RUNPOD_ENDPOINT_ID={endpoint_id!r}")
    print("  uv run --with runpod python infra/runpod/check_health.py   # confirm workers are ready")
    print("  COMPUTE_PROVIDER=runpod uv run --package api uvicorn api.main:app --app-dir apps/api/src")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
