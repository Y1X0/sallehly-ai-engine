# infra/runpod

RunPod Serverless Endpoint deployment configuration for `workers/gpu-worker`
(the container image `RunPodProvider` submits jobs to). Holds endpoint
definitions: image reference, GPU type selection, min/max worker count,
idle timeout.

**Status:** Phase 3 target — see `docs/adr/0005-gpu-provider-runpod-vastai-first.md`.
