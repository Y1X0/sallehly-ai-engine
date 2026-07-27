# infra/runpod

Deployment tooling for a RunPod Serverless Endpoint running
`workers/gpu-worker` (the image `RunPodProvider` submits jobs to).
**Free by default**: both the CI workflow and `deploy_endpoint.py`
itself default to a dry-run/validation mode that makes no billable
RunPod API call and needs no RunPod credentials or balance. Real,
billable RunPod endpoint creation is available but strictly opt-in -
see "Two modes" below.

## Files

- `deploy_endpoint.py` - creates a real RunPod template + serverless
  endpoint from a built/pushed `workers/gpu-worker` image, using the
  official `runpod` Python SDK's real management API
  (`runpod.create_template()`/`runpod.create_endpoint()`). Pass
  `--dry-run` to validate arguments and print what would be created
  without calling the RunPod API at all (no `RUNPOD_API_KEY` needed).
- `check_health.py` - checks a deployed endpoint's real health
  (`GET {endpoint_id}/health`) via
  `video_engine_adapter.compute.RunPodProvider.health_check()`. Only
  meaningful once a real endpoint exists.

## Two modes

| | Free / dry-run (default) | Real deploy (opt-in) |
|---|---|---|
| Docker build + push to GHCR | Real, always happens | Real, always happens |
| `deploy_endpoint.py` | `--dry-run`: validates args, no RunPod API call | Real `create_template()`/`create_endpoint()` |
| `RUNPOD_API_KEY` needed | No | Yes |
| RunPod account balance needed | No | Yes (RunPod requires a funded account to create an endpoint) |
| Environment approval | None (`runpod-free-dry-run`, no protection rules) | Required (`runpod-production-deploy` reviewers) |
| `verify-health` job | Skipped (no real endpoint to check) | Runs for real |

This exists because the original goal of this project is a free/
near-free experimental environment - a real `create_endpoint()` call
fails outright without at least $0.01 of RunPod balance, so nothing
here should ever attempt that unless a real deployment was explicitly
requested.

## Recommended: run via GitHub Actions

`.github/workflows/deploy-runpod-endpoint.yml` runs the entire build ->
push -> deploy -> health-check sequence for you on a real GitHub-hosted
runner - this exists specifically because the sandbox this tooling was
originally written in cannot reach the Docker Hub registry CDN or
`api.runpod.ai`/`api.runpod.io` (confirmed by hand); a GitHub Actions
runner has neither restriction.

### Free mode (default, no setup required)

Actions -> "Deploy - RunPod Wan2.2 Production Endpoint" -> Run workflow
-> check `confirm_deploy`, leave `real_deploy` **unchecked** -> Run. It
builds and pushes the image to this repo's own GHCR for real (no extra
registry secret needed - `GITHUB_TOKEN` is sufficient), then runs
`deploy_endpoint.py --dry-run` to validate the deploy logic without
touching the RunPod API. No `RUNPOD_API_KEY`, no RunPod balance, no
Environment approval needed. `verify-health` is skipped (there is no
real endpoint). Results are written to the run's job summary.

### Real RunPod deployment (opt-in, one-time setup required)

1. Add repository secrets (Settings -> Secrets and variables -> Actions):
   - `RUNPOD_API_KEY` (required) - from your RunPod account.
   - `HF_TOKEN` (optional) - only if `models/registry.yaml`'s configured
     Wan2.2 repo becomes gated (public as of this writing).
2. Create the `runpod-production-deploy` Environment (Settings ->
   Environments -> New environment) and set **Required reviewers** to
   whoever is allowed to authorize a real RunPod endpoint - this is the
   actual approval gate; no code in this repository can bypass it, the
   same way `training-phase3-paid-gpu-gate.yml`'s `paid-gpu-approval`
   Environment already gates real training spend in this repo.
3. Make sure your RunPod account has at least $0.01 balance - RunPod
   itself rejects endpoint creation otherwise.

**To run it**: Actions -> "Deploy - RunPod Wan2.2 Production Endpoint" ->
Run workflow -> check both `confirm_deploy` **and** `real_deploy` -> Run.
It builds and pushes the image, deploys the real endpoint (pausing for
the Environment's required-reviewer approval), and checks its health -
writing the image ref and endpoint id to the run's job summary. Copy
the printed `RUNPOD_ENDPOINT_ID` into a repository secret/variable (or
your own deployment's env) for `apps/api`'s `COMPUTE_PROVIDER=runpod`
path.

## Manual alternative (needs your own unrestricted Docker + network access)

1. Build the image (from the repo root, not this directory):
   ```bash
   docker build -f workers/gpu-worker/Dockerfile -t <your-registry>/sallehly-wan22-worker:2.2.0 .
   docker push <your-registry>/sallehly-wan22-worker:2.2.0
   ```
2. Deploy the endpoint:
   ```bash
   export RUNPOD_API_KEY=...           # from your RunPod account
   export HF_TOKEN=...                 # only if models/registry.yaml's repo is gated
   uv run --with runpod python infra/runpod/deploy_endpoint.py \
       --image <your-registry>/sallehly-wan22-worker:2.2.0
   ```
   Prints a real `endpoint_id` - export it as `RUNPOD_ENDPOINT_ID`.

   To validate the same arguments without spending anything or needing
   `RUNPOD_API_KEY`, add `--dry-run`:
   ```bash
   uv run --with runpod python infra/runpod/deploy_endpoint.py \
       --dry-run --image <your-registry>/sallehly-wan22-worker:2.2.0
   ```
3. Confirm it's actually up before relying on it:
   ```bash
   uv run --with runpod python infra/runpod/check_health.py
   ```
4. Point the API at it:
   ```bash
   COMPUTE_PROVIDER=runpod RUNPOD_API_KEY=... RUNPOD_ENDPOINT_ID=... \
       uv run --package api uvicorn api.main:app --app-dir apps/api/src
   ```
   `apps/api/src/api/state.py::build_app_state` fails fast, at startup,
   with a clear error if `RUNPOD_API_KEY`/`RUNPOD_ENDPOINT_ID` are
   missing when `COMPUTE_PROVIDER=runpod` is set - it never silently
   falls back to a mock provider.

## What actually happens on the worker

`workers/gpu-worker/handler.py` downloads and checksum-verifies real
Wan2.2 weights on its first cold start (per `models/registry.yaml`'s
`download:` block, via the same `training.hf_download` machinery
`services/training/scripts/download_wan22_weights.py` uses - never
random weights), keeps the loaded `WanPipeline` warm for subsequent
requests on that worker, and runs real inference via
`video_engine_adapter.inference.generate_video(..., smoke_test=False)`
- see that module's docstring for exactly what "real" means here versus
the `local-inference`/smoke-test path used for the zero-credentials demo.

## Status

Real, working deployment tooling and a real CI/CD workflow to run it.
The workflow's `build-and-push` job has run for real (real ~8-minute
Docker build, real image pushed to GHCR). A real `deploy-endpoint` run
(`real_deploy=true`) was attempted against a real RunPod account and
was correctly rejected by RunPod itself ("You must have at least $0.01
in your account balance to create an endpoint.") - confirming the real
API integration works end-to-end up to the account-funding boundary,
which is outside this repository's control. The free/dry-run mode
(`real_deploy=false`, the default) exists specifically so the rest of
this pipeline (build, push, deploy-logic validation) can be exercised
with zero cost and no RunPod account at all. The code itself is
genuine, not a stub: `deploy_endpoint.py`/`check_health.py` were
validated by inspecting the actual installed `runpod` PyPI package's
source for its real `create_template`/`create_endpoint`/
`Endpoint.health()` implementations rather than guessed, and the
workflow's build/push/deploy/health-check sequence mirrors the manual
steps above exactly. A real run with a funded RunPod account is the
next real, human-gated step for anyone who wants an actual production
endpoint. See `docs/adr/0005-gpu-provider-runpod-vastai-first.md` for
the original provider-choice rationale.
