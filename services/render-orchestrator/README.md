# services/render-orchestrator

## GenerationPipeline (Phase 3) + ProjectLifecycle/Orchestrator/Workflow (Phase 4)

**Responsibility:** everything from "a render plan exists" to "GPU
generation finished" (`GenerationPipeline`), and everything from "a
project is created" to "a generated video asset exists"
(`ProjectLifecycle`, orchestrated either synchronously or by a durable
Temporal workflow).

## Contents

```
jobs.py               GenerationJob / GenerationJobStatus / IGenerationJobStore  (Phase 3)
pipeline.py            GenerationPipeline - RenderSpec -> engine -> compute -> AssetManager (Phase 3)
events.py               EventType / Event / IEventBus  (Phase 4)
project_lifecycle.py    ProjectLifecycle - the one place the full-lifecycle business logic lives (Phase 4)
orchestrator.py         IProjectOrchestrator / SyncProjectOrchestrator - what apps/api depends on (Phase 4)
workflows/
  activities.py          Temporal @activity.defn wrappers around ProjectLifecycle
  render_workflow.py      Temporal @workflow.defn ProjectGenerationWorkflow
```

## Three layers

1. **`GenerationPipeline`** (Phase 3): `RenderSpec` dict → `IVideoEngine`
   + `IComputeProvider` → `GenerationJob` → `AssetManager`. See
   `docs/adr/0009-generation-pipeline.md`.
2. **`ProjectLifecycle`** (Phase 4): the full flow -
   `create_project → generate_creative_plan → approve/reject_storyboard →
   approve/reject_render_plan → generate_video` - composing
   `CreativeDirector` + `CreativeCompiler` + `GenerationPipeline` +
   `IProjectStore`, publishing an `Event` at every transition. **This is
   the only place this logic lives** - see
   `docs/adr/0010-persistence-and-lifecycle.md`.
3. **Two drivers of `ProjectLifecycle`**, same method calls either way:
   - **`SyncProjectOrchestrator`** (`orchestrator.py`): synchronous,
     in-process. What `apps/api` and every test in this repo use.
   - **`ProjectGenerationWorkflow`** (`workflows/`): a real Temporal
     workflow whose activities (`workflows/activities.py`) each call one
     `ProjectLifecycle` method. Durable - survives a worker crash,
     resumes from Temporal's replayed event history - which
     `SyncProjectOrchestrator` cannot do. **Not executable in this
     environment**: `temporalio.testing.WorkflowEnvironment`'s ephemeral
     test server downloads a native binary from `temporal.download` on
     first use, which this sandbox's network policy blocks (the same
     class of limitation as Phase 3's live GPU inference). The workflow/
     activity definitions are verified to register correctly with the
     `temporalio` SDK (decorators, signal/query names) but have not been
     executed end-to-end against a live or ephemeral Temporal server -
     see `docs/adr/0010-persistence-and-lifecycle.md` for exactly what
     was and wasn't verifiable here.

## Interface

```python
from render_orchestrator import GenerationPipeline, ProjectLifecycle, SyncProjectOrchestrator

pipeline = GenerationPipeline(engine=Wan21Adapter(), compute_provider=LocalProvider())
lifecycle = ProjectLifecycle(creative_director, creative_compiler, pipeline, project_store, memory)
orchestrator = SyncProjectOrchestrator(lifecycle)

record = orchestrator.create_project(workspace_id="ws1", created_by="u1", prompt="...", target_duration_sec=12, aspect_ratio="16:9")
orchestrator.generate_creative_plan(record.project_id)
orchestrator.approve_storyboard(record.project_id)
orchestrator.approve_render_plan(record.project_id)
record = orchestrator.generate_video(record.project_id)  # -> COMPLETED, asset_ids populated
```

Neither `ProjectLifecycle` nor `GenerationPipeline` nor anything above
them in the call stack (`CreativeCompiler`, `CreativeDirector`) is
coupled to Wan2.1, Claude, or Temporal specifically - every dependency is
injected already configured. See ADR 0001, 0002, 0009, 0010.

## Status (Phase 4)

`GenerationPipeline` (Phase 3), `ProjectLifecycle`, `SyncProjectOrchestrator`,
`IEventBus`, and the Temporal workflow/activity definitions are all
implemented. The full project lifecycle - including the reject/
regenerate path on both approval gates and the generation failure path -
is tested end-to-end through `apps/api`'s real HTTP endpoints
(`tests/test_api.py`) and directly (`tests/test_project_lifecycle.py`,
`tests/test_project_orchestrator.py`).
