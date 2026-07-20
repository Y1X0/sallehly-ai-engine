# ADR 0005: Start GPU compute on RunPod + Vast.ai, defer Kubernetes

**Status:** Accepted (per explicit decision from the project owner: avoid
Kubernetes complexity initially, optimize for lowest cost during early
experiments)

## Context

Running and maintaining a Kubernetes GPU node pool (device plugins,
autoscaling, node provisioning, cluster upgrades) is significant
operational overhead that is not justified before the pipeline itself
(AI Director → Compiler → Wan2.1) has been validated end-to-end, and
before render volume is high enough to need dedicated infrastructure.
RunPod Serverless and Vast.ai both offer on-demand GPU access with
effectively zero infrastructure to manage, at the cost of somewhat higher
per-hour/per-request pricing than self-hosted hardware at scale.

## Decision

Phase 0-3 target two `IComputeProvider` implementations:

- **`RunPodProvider`** — RunPod Serverless Endpoints. Request/response
  model: POST the job, poll `/status/{id}`, GET the result. Best fit for
  spiky, low-volume early usage since there is no idle cost between
  requests.
- **`VastAIProvider`** — a rented on-demand Vast.ai GPU instance running
  the same `workers/gpu-worker` image behind a thin self-hosted
  job-runner HTTP service (`infra/vastai/`, Phase 3). Used when a
  longer-lived, cheaper-per-hour instance makes more sense than
  per-request Serverless pricing (e.g. batch/background rendering).

Kubernetes is deferred to Phase 7 as a third `IComputeProvider`
(`KubernetesProvider`), added only once volume/cost data justifies the
operational investment — see ADR 0002 for why this swap costs nothing
upstream.

## Consequences

- Phase 0-3 has no Kubernetes manifests to write or maintain; `infra/kubernetes/`
  exists as a placeholder only.
- `infra/runpod/` holds RunPod Serverless Endpoint deployment config
  (the image reference, GPU type selection, min/max workers) as the
  primary Phase 3 deployment target.
- Cost/latency data collected while running on RunPod/Vast.ai directly
  informs whether/when Phase 7's Kubernetes migration is worth doing at
  all — it may turn out unnecessary if usage never reaches the volume
  where self-hosting is cheaper.
