# workers/gpu-worker

The container image that actually runs on rented GPU hardware. This is
what `EngineJobPayload.container_image` points to, and what both
`RunPodProvider` and `VastAIProvider` deploy/invoke — the same image
either way, since the whole point of `IComputeProvider` is that the
worker doesn't know or care which provider launched it.

- `handler.py` — the entrypoint. `run(job)` downloads/verifies real
  Wan2.2 weights (`training.hf_download`, never random weights), builds
  a real `diffusers.WanPipeline` (`video_engine_adapter.inference`),
  runs real inference, uploads the result via `storage_sdk`, and
  returns `{"output_uri": ..., "engine_metadata": {...}}`. Wraps `run()`
  in the RunPod Serverless SDK's handler protocol when run on RunPod
  (`runpod.serverless.start`); the Vast.ai job-runner (Phase 3,
  `infra/vastai/`) would call the same `run()` function directly with a
  `{"id": ..., "input": {...}}` dict.
- `Dockerfile` — CUDA base image with this repo's own real packages
  (`video-engine-adapter[real-inference]`, `training[gpu-training]`)
  installed in. Build from the repo root - see `infra/runpod/README.md`
  for the full build → push → deploy → health-check sequence.

**Status:** Real, not a stub - `handler.py`'s real HF-download step was
exercised end-to-end in the sandbox this was built in, up to that
sandbox's own network restriction on huggingface.co (a previously
documented limitation, see docs/EXECUTION_PLAN_FIRST_GPU_RUN.md); the
`Dockerfile` itself was not build-tested here (this sandbox's own
network restriction also blocks pulling any Docker Hub base image, not
specific to this image) - build it for real once you have a normal
Docker environment, per `infra/runpod/README.md`.
