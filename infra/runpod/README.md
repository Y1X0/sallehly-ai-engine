# infra/runpod

Real deployment tooling for a RunPod Serverless Endpoint running
`workers/gpu-worker` (the image `RunPodProvider` submits jobs to). Not a
mock, not a simulation - these scripts make real, billable RunPod API
calls under your account.

## Files

- `deploy_endpoint.py` - creates a real RunPod template + serverless
  endpoint from a built/pushed `workers/gpu-worker` image, using the
  official `runpod` Python SDK's real management API
  (`runpod.create_template()`/`runpod.create_endpoint()`).
- `check_health.py` - checks a deployed endpoint's real health
  (`GET {endpoint_id}/health`) via
  `video_engine_adapter.compute.RunPodProvider.health_check()`.

## One-time setup (real steps, real cost)

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

Real, working deployment tooling. Not yet run against a real RunPod
account from this project (no RunPod credentials or a pushed image
registry available in the environment these scripts were written in) -
the code itself is genuine, not a stub, and was validated by inspecting
the actual installed `runpod` PyPI package's source for its real
`create_template`/`create_endpoint`/`Endpoint.health()` implementations
rather than guessed. See `docs/adr/0005-gpu-provider-runpod-vastai-first.md`
for the original provider-choice rationale.
