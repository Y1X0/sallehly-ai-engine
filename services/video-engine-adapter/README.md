# services/video-engine-adapter

Concrete implementations of the two interfaces defined in
`packages/video-engine-sdk`. This is the **only** place in the codebase
that is allowed to know engine-specific or provider-specific details.

## Contents

```
adapters/
  wan21_adapter.py   Wan21Adapter(IVideoEngine)  - maps RenderSpec <-> Wan2.1 native args
compute/
  runpod_provider.py  RunPodProvider(IComputeProvider)  - RunPod Serverless (production HTTP client)
  vastai_provider.py  VastAIProvider(IComputeProvider)  - rented Vast.ai instance
  local_provider.py   LocalProvider(IComputeProvider)   - no-GPU dev/test stub
registry.py            register_defaults() - wires the above into config_sdk's registries
```

## Selection

`register_defaults()` (called once at process/app startup) registers
every engine/compute-provider this package ships into `config_sdk`'s
shared registries, keyed by the same strings used in `.env`
(`VIDEO_ENGINE`, `COMPUTE_PROVIDER`):

```python
import video_engine_adapter  # runs register_defaults() via its __init__
from config_sdk import VIDEO_ENGINE_REGISTRY, COMPUTE_PROVIDER_REGISTRY

engine = VIDEO_ENGINE_REGISTRY.create(settings.video_engine)               # Wan21Adapter()
compute = COMPUTE_PROVIDER_REGISTRY.create(
    settings.compute_provider, api_key=..., endpoint_id=...
)  # RunPodProvider(...) / LocalProvider() / VastAIProvider(...)
```

Adding a second engine or provider means adding one file here and one
`register_if_absent(...)` call in `registry.py` - no changes to any
Planner, the Compiler, or `services/render-orchestrator`'s
`GenerationPipeline`.

## Current status (Phase 3)

- **`Wan21Adapter`**: fully implemented - `capabilities()`,
  `build_job_payload()` (including image-to-video conditioning image
  mapping and seed omission when unset), `parse_result()`. See
  `docs/adapters/wan21-adapter-spec.md`.
- **`LocalProvider`**: fully functional (unchanged since Phase 0) - no
  GPU, no network, writes a JSON stub and reports success immediately.
  This is what `GenerationPipeline` runs against in tests.
- **`RunPodProvider`**: fully implemented against the real RunPod
  Serverless HTTP API (`httpx`), with retry-with-backoff on transient
  errors (5xx, connection failures) and fail-fast on 4xx. Tested against
  `httpx.MockTransport` - never against a live RunPod account in this
  environment (see `tests/test_runpod_provider.py`).
- **`VastAIProvider`**: still a Phase 3+ stub (`NotImplementedError`) -
  Vast.ai's rented-instance model needs a companion self-hosted
  job-runner service (`infra/vastai/`) that doesn't exist yet; RunPod was
  prioritized as the first production-ready provider.

Actually running Wan2.1 end-to-end still requires deploying
`workers/gpu-worker` with real model weights onto a RunPod endpoint -
that is an infrastructure/deployment step, not something this repository
can execute in this environment. What's implemented here is everything
up to that boundary: a correct, tested request/response contract on both
sides of it.
