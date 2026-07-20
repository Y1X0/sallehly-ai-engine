# workers/gpu-worker

The container image that actually runs on rented GPU hardware. This is
what `EngineJobPayload.container_image` points to, and what both
`RunPodProvider` and `VastAIProvider` deploy/invoke — the same image
either way, since the whole point of `IComputeProvider` is that the
worker doesn't know or care which provider launched it.

- `handler.py` — the entrypoint. Wraps `run()` in the RunPod Serverless
  SDK's handler protocol when run on RunPod; the Vast.ai job-runner
  (Phase 3, `infra/vastai/`) calls the same `run()` function directly.
- `Dockerfile` — CUDA base image; Wan2.1 itself gets vendored in during
  Phase 3.

**Status:** Phase 3 target. Structurally complete, inference call not
yet implemented (see `docs/adapters/wan21-adapter-spec.md`).
