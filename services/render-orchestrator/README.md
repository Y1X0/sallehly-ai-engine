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
events.py               EventType / Event / IEventBus / InMemoryEventBus  (Phase 4; POST_PROCESSING_STARTED/EXPORT_COMPLETED/EXPORT_FAILED added Phase 8)
redis_event_bus.py      RedisEventBus(IEventBus) - real Redis pub/sub delivery (Phase 8 WP3)
project_lifecycle.py    ProjectLifecycle - the one place the full-lifecycle business logic lives (Phase 4; finalize_project + Cinematic Intelligence enrichment added Phase 8)
orchestrator.py         IProjectOrchestrator / SyncProjectOrchestrator - what apps/api depends on (Phase 4)
post_production.py      PostProductionRunner - bridges GenerationPipeline's clips into the Phase 6 post-production pipeline (Phase 8)
workflows/
  activities.py          Temporal @activity.defn wrappers around ProjectLifecycle
  render_workflow.py      Temporal @workflow.defn ProjectGenerationWorkflow (one @workflow.update per IProjectOrchestrator method - Phase 8 WP6)
  temporal_orchestrator.py TemporalProjectOrchestrator(IProjectOrchestrator) - the durable driver (Phase 8 WP6)
  worker.py               build_worker() - Worker hosting the workflow/activities (Phase 8 WP6)
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
   `docs/adr/0010-persistence-and-lifecycle.md`. Two optional Phase 8
   additions (`docs/adr/0014-pipeline-integration.md`): if a
   `CinematicIntelligenceCoordinator` is injected, `approve_storyboard`/
   `reject_render_plan` enrich the compiled `RenderPlan`'s prompts before
   gate 2; if a `PostProductionRunner` is injected, a new
   `finalize_project(project_id)` method (`completed → post_processing →
   exported`) assembles the generated shots into one deliverable. Both
   are `None` by default - every pre-Phase-8 caller is unaffected.
3. **Two drivers of `ProjectLifecycle`**, same method calls either way -
   selected via `Settings.orchestrator` (`"sync"` default / `"temporal"`,
   `apps/api/state.py`):
   - **`SyncProjectOrchestrator`** (`orchestrator.py`): synchronous,
     in-process. The default for `apps/api` and every test in this repo.
   - **`TemporalProjectOrchestrator`** (`workflows/temporal_orchestrator.py`):
     starts/updates a real `ProjectGenerationWorkflow` via a
     `temporalio.client.Client`. Durable - survives a worker crash,
     resumes from Temporal's replayed event history - which
     `SyncProjectOrchestrator` cannot do. **Genuinely executed as of
     Phase 8 WP6** (`docs/adr/0015-temporal-activation.md`): a real
     `temporal` CLI dev server (downloaded from GitHub Releases, not
     through the SDK's own blocked auto-downloader) plus a real worker
     (`workflows/worker.py`) are driven end-to-end in
     `tests/test_temporal_orchestrator.py`, including a worker-restart
     durability test. Requires a running worker process
     (`apps/api/src/api/temporal_worker.py`) - see that ADR's
     Consequences for the one real limitation today's in-memory stores
     put on running the worker as a genuinely separate OS process.
     **That limitation is fixed as of Phase 8 WP2**
     (`docs/adr/0016-postgres-persistence.md`): `PostgresProjectStore`
     (`packages/persistence`, `PROJECT_STORE=postgres`) gives the API
     and worker processes a real shared backing store, so they no
     longer need to share one in-process `InMemoryProjectStore`.

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

## Status (Phase 4, extended Phase 8)

`GenerationPipeline` (Phase 3), `ProjectLifecycle`, `SyncProjectOrchestrator`,
`IEventBus`, and the Temporal workflow/activity definitions are all
implemented. The full project lifecycle - including the reject/
regenerate path on both approval gates and the generation failure path -
is tested end-to-end through `apps/api`'s real HTTP endpoints
(`tests/test_api.py`) and directly (`tests/test_project_lifecycle.py`,
`tests/test_project_orchestrator.py`). `PostProductionRunner` and
Cinematic Intelligence enrichment (Phase 8) are tested the same way,
including `finalize_project`'s failure path against `LocalProvider`'s
placeholder output and its success path against real ffmpeg-generated
clips - see `docs/adr/0014-pipeline-integration.md`. `TemporalProjectOrchestrator`
(Phase 8 WP6) is tested the same rigorous way: real, live execution
against an actual `temporal` CLI dev server and worker, not mocked - see
`docs/adr/0015-temporal-activation.md`.
