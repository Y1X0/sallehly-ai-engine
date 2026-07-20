# ADR 0002: Split "which video model" from "where it runs"

**Status:** Accepted

## Context

ADR 0001 established that the video engine (Wan2.1 today, a custom
foundation model later) must be swappable. Separately, the GPU hosting
strategy is also expected to change over time: starting on RunPod
Serverless and rented Vast.ai instances to minimize cost/complexity during
early experiments (see ADR 0005), and moving to a self-managed Kubernetes
GPU pool once render volume justifies the operational overhead.

If `IVideoEngine` were the only abstraction and it also handled job
submission/polling/result-fetching against a specific compute backend, a
GPU-provider migration would force changes to every model adapter, and a
model migration would force changes to every provider integration —
these are independent axes of change and bundling them creates
unnecessary coupling.

## Decision

Two interfaces (`packages/video-engine-sdk`):

- `IVideoEngine` — knows the model. `capabilities()` describes what it
  can do; `build_job_payload(RenderSpec)` builds the model's native
  input; `parse_result(spec, output)` normalizes the model's native
  output back into a `RawClip`.
- `IComputeProvider` — knows the infrastructure. `submit(payload)`,
  `get_status(handle)`, `fetch_output(handle)`, `cancel(handle)` — it
  never inspects `payload.input`, it just gets `EngineJobPayload` onto a
  GPU and the result back.

`services/render-orchestrator` is the only service that wires a chosen
engine and a chosen provider together, driven by config
(`VIDEO_ENGINE`, `COMPUTE_PROVIDER`).

## Consequences

- `Wan21Adapter` (an `IVideoEngine`) is completely unaware of whether it
  is running on RunPod, Vast.ai, or (later) an in-house Kubernetes pool.
- `RunPodProvider`/`VastAIProvider`/future `KubernetesProvider` (all
  `IComputeProvider`) are completely unaware of which model they are
  running — they treat `EngineJobPayload.input` as an opaque blob.
- RunPod's request/response Serverless model and Vast.ai's rented-instance
  model are different execution shapes under the hood; both are made to
  fit the same four-method contract (Vast.ai's provider talks to a thin
  self-hosted job-runner HTTP service deployed onto the rented instance,
  see `services/video-engine-adapter/README.md`), so the Render
  Orchestrator never needs a provider-specific code path.
- One extra interface and one extra wiring step in Phase 0, in exchange
  for the compute-provider migration in Phase 7 touching zero business
  logic.
