# packages/video-engine-sdk

Two interfaces, deliberately kept separate:

```
IVideoEngine        -> WHICH MODEL runs, and how to talk to it
IComputeProvider     -> WHERE it runs (which GPU host)
```

## Why two interfaces instead of one

The original ask was "swap Wan2.1 for my own model later without
rewriting the system." That alone only requires `IVideoEngine`. But this
project's GPU strategy is *also* expected to evolve — starting on RunPod
Serverless / rented Vast.ai instances (cheapest way to run early
experiments) and moving to a self-managed Kubernetes GPU pool once volume
justifies it (see `docs/adr/0005-gpu-provider-runpod-vastai-first.md`).

Those are two independent axes of change. Bundling them into one
interface would mean a GPU-provider migration forces changes to every
model adapter, and a model migration forces changes to every
provider integration. Splitting them means:

- `Wan21Adapter implements IVideoEngine` — unaffected by which compute
  provider is active.
- `RunPodProvider`, `VastAIProvider`, later `KubernetesProvider`, all
  `implement IComputeProvider` — unaffected by which model is active.

The Render Orchestrator (`services/render-orchestrator`) is the only
service that wires a chosen `IVideoEngine` and a chosen `IComputeProvider`
together, driven entirely by config (`VIDEO_ENGINE`, `COMPUTE_PROVIDER` in
`.env`).

## Execution flow

```
RenderSpec
   -> engine.build_job_payload(spec)      -> EngineJobPayload
   -> compute.submit(payload)              -> ComputeJobHandle
   -> compute.get_status(handle)  (poll)   -> ComputeJobStatus
   -> compute.fetch_output(handle)         -> EngineJobOutput
   -> engine.parse_result(spec, output)    -> RawClip
```

## Implementations

| Interface | Implementation | Location | Status |
|---|---|---|---|
| `IVideoEngine` | `Wan21Adapter` | `services/video-engine-adapter/src/video_engine_adapter/adapters/wan21_adapter.py` | Phase 3 target, stubbed now |
| `IComputeProvider` | `RunPodProvider` | `.../compute/runpod_provider.py` | Phase 3 target, stubbed now |
| `IComputeProvider` | `VastAIProvider` | `.../compute/vastai_provider.py` | Phase 3 target, stubbed now |
| `IComputeProvider` | `LocalProvider` | `.../compute/local_provider.py` | Dev/testing only — runs a mock engine with no GPU, so the whole pipeline is testable locally |
| `IComputeProvider` | `KubernetesProvider` | *(not started)* | Phase 7, once GPU volume justifies self-hosting |
