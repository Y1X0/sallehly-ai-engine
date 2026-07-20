# ADR 0009: GenerationPipeline as the sole bridge from RenderSpec to a concrete engine

**Status:** Accepted

## Context

Phase 1/2 deliberately kept `CreativeDirector` and `CreativeCompiler`
producing plain, JSON-Schema-validated dicts (`director_plan`,
`storyboard`, `render_plan`/`render_configuration`) with zero knowledge
of Wan2.1, RunPod, or any other execution detail (ADR 0001). Phase 3
needs to actually run a `RenderSpec` through a real `IVideoEngine` +
`IComputeProvider` pair without breaking that separation, and needs a
concrete answer for three things ADR 0001/0002 anticipated but didn't
yet implement: job lifecycle tracking, a place for the dict-shaped
`RenderSpec` to become the typed dataclass `IVideoEngine.build_job_payload`
expects, and where a generated asset's metadata lives.

## Decision

### 1. `GenerationPipeline` (`services/render-orchestrator/pipeline.py`) is the only bridge

It is constructed with a concrete `IVideoEngine` and `IComputeProvider`
(chosen via `config_sdk`'s registries, see `video_engine_adapter.register_defaults()`)
and is the **only** class in the codebase that:
- converts a `render_configuration.schema.json`-shaped dict into a
  `video_engine_sdk.types.RenderSpec` dataclass (`_render_spec_from_dict`)
- calls `IVideoEngine`/`IComputeProvider` methods directly

`CreativeDirector` and `CreativeCompiler` remain completely unaware this
class exists. Nothing about them changed in Phase 3.

### 2. Job lifecycle: `GenerationJob` (queued/running/completed/failed)

A new schema, `generation_job.schema.json`, and a mutable dataclass
(`GenerationJob`, deliberately not frozen - unlike the value objects
elsewhere in this codebase, a job has identity and evolving state) with
an in-memory store today (`InMemoryGenerationJobStore`) and a Postgres-
backed one as a natural later swap (same `IGenerationJobStore` interface,
same pattern as `IDirectorMemoryStore` in Phase 1).

Status names (`queued`/`running`/`completed`/`failed`) are deliberately
different from `video_engine_sdk.ComputeJobStatus`'s (`queued`/`running`/
`succeeded`/`failed`/`cancelled`) - a `GenerationJob` is the
platform's own business object; `ComputeJobStatus` is what a specific
compute provider reports. `GenerationPipeline` maps between them
(`succeeded -> completed`; anything else on failure, including
`cancelled`, becomes `failed` with an explanatory `error_message`).

### 3. Asset registration: `AssetManager` + `packages/storage-sdk`

`AssetManager` (`services/asset-manager`) is a versioned registry -
`asset_record.schema.json` - that records where a `RawClip` (or any
other generated/uploaded asset) already lives. It does not require
`packages/storage-sdk`'s `IStorageProvider` for this - `RawClip.storage_uri`
already points somewhere valid (a compute provider's upload target, or
`LocalProvider`'s local stub file). `IStorageProvider` is prepared
(`LocalFilesystemStorageProvider` implemented) for the distinct, later
need of the platform copying/persisting bytes it owns (e.g. a
Post-Processing master, Phase 5) - it is not on the Phase 3 critical
path and `AssetManager` only uses it if explicitly asked to
(`persist_local_copy`).

### 4. Retry semantics, two layers

- `GenerationPipeline.generate_shot` retries the **whole submit-poll-fetch
  cycle** up to `max_retries` times on any exception, recording
  `retry_count`/`error_message` on the `GenerationJob`.
- `RunPodProvider` additionally retries individual **HTTP requests**
  (connection errors, 5xx) with backoff before that exception ever
  reaches `GenerationPipeline` - a 4xx (bad request/auth) fails
  immediately since retrying the same request cannot change the outcome.

These are independent: a transient RunPod 500 is usually absorbed at the
HTTP layer and never becomes a job-level retry at all.

## Consequences

- Swapping Wan2.1 for a custom foundation model, or RunPod for
  Kubernetes, means constructing `GenerationPipeline` with different
  `engine`/`compute_provider` instances - no change to `pipeline.py`
  itself, and zero change to `CreativeDirector`/`CreativeCompiler`. This
  is the concrete mechanism ADR 0001/0002 promised.
- An `IImageEngine` (see `docs/ARCHITECTURE.md`'s forward-compatibility
  note) would plug into a sibling `GenerationPipeline`-like class reusing
  the same `IComputeProvider` implementations, `GenerationJob` shape, and
  `AssetManager` - none of Phase 3's code assumes "video" beyond the
  `IVideoEngine`/`RawClip` types themselves.
- `workers/gpu-worker/handler.py`'s actual Wan2.1 inference call remains
  `NotImplementedError` - deploying real model weights onto a GPU is an
  infrastructure/ops step outside what this repository can execute in
  this environment. Everything on the code side of that boundary
  (`Wan21Adapter`, `RunPodProvider`, `GenerationPipeline`) is implemented
  and tested against mocks/`LocalProvider`.
