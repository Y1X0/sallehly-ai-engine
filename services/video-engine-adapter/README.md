# services/video-engine-adapter

Concrete implementations of the two interfaces defined in
`packages/video-engine-sdk`. This is the **only** place in the codebase
that is allowed to know engine-specific or provider-specific details.

## Contents

```
adapters/
  wan21_adapter.py   Wan21Adapter(IVideoEngine)  - maps RenderSpec <-> Wan2.1 native args
compute/
  runpod_provider.py  RunPodProvider(IComputeProvider)  - RunPod Serverless
  vastai_provider.py  VastAIProvider(IComputeProvider)  - rented Vast.ai instance
  local_provider.py   LocalProvider(IComputeProvider)   - no-GPU dev/test stub
```

## Selection

The Render Orchestrator picks one adapter and one compute provider purely
from config (`VIDEO_ENGINE`, `COMPUTE_PROVIDER` in `.env`):

```python
engine = ENGINE_REGISTRY[settings.VIDEO_ENGINE]()          # e.g. Wan21Adapter()
compute = COMPUTE_REGISTRY[settings.COMPUTE_PROVIDER](...)  # e.g. RunPodProvider(...)
```

Adding a second engine or provider means adding one file here and one
registry entry — no changes to any Planner, the Compiler, or the
Orchestrator's control flow.

## Current status (Phase 0)

All three compute providers and the Wan2.1 adapter are structurally
complete (method signatures, capability manifest, RenderSpec -> native
payload mapping) but raise `NotImplementedError` in the actual
network/subprocess call sites — those are filled in during Phase 3. The
exception is `LocalProvider`, which is fully functional today: it writes
the payload to disk and reports success immediately, so the rest of the
pipeline can be built and tested end-to-end before any real GPU work is
wired up.

See `docs/adapters/wan21-adapter-spec.md` for the full field-by-field
mapping this adapter implements.
