# apps/api

Public/internal API gateway (BFF). Route handlers are thin: every one of
them calls `state.orchestrator` (an `IProjectOrchestrator`,
`services/render-orchestrator`) or reads directly from `state.job_store`/
`state.asset_manager` - no creative/rendering logic lives here.

See `docs/api/openapi.yaml` for the full contract, `docs/ARCHITECTURE.md`
for where this sits in the pipeline, and
`docs/adr/0010-persistence-and-lifecycle.md` for why route handlers
depend on `IProjectOrchestrator` rather than calling
`CreativeDirector`/`CreativeCompiler`/`GenerationPipeline` individually.

## Endpoints

| Method & Path | Calls |
|---|---|
| `POST /projects` | `orchestrator.create_project` |
| `GET /projects/{id}` | `project_store.get` |
| `POST /projects/{id}/generate-plan` | `orchestrator.generate_creative_plan` |
| `POST /projects/{id}/approve-storyboard` | `orchestrator.approve_storyboard` |
| `POST /projects/{id}/reject-storyboard` | `orchestrator.reject_storyboard` (regenerates the storyboard using the feedback) |
| `POST /projects/{id}/approve-render` | `orchestrator.approve_render_plan` |
| `POST /projects/{id}/reject-render` | `orchestrator.reject_render_plan` (recompiles the render plan, optionally with a new `quality_tier`) |
| `POST /projects/{id}/generate-video` | `orchestrator.generate_video` |
| `GET /projects/{id}/assets` | `asset_manager.get` for each of the project's `asset_ids` |
| `GET /jobs/{id}` | `job_store.get` |
| `GET /jobs/{id}/status` | `job_store.get` (status/retry_count/error_message only) |

A `409` is returned when a request doesn't match the project's current
`ProjectStatus` (e.g. approving a storyboard that isn't
`waiting_storyboard_approval`) - see `ProjectLifecycleError`.

## Wiring (`state.py`)

`build_app_state()` runs once at startup (FastAPI `lifespan`) and is the
**only** place that reads `LLM_PROVIDER`/`COMPUTE_PROVIDER` config and
picks a concrete `ILLMProvider`/`IVideoEngine`/`IComputeProvider`. In this
environment (and by default anywhere `ANTHROPIC_API_KEY`/`RUNPOD_API_KEY`
aren't set), that resolves to `LocalHeuristicLLMProvider` + `Wan21Adapter`
+ `LocalProvider` - fully offline, no GPU, no API key, which is what lets
this API be exercised end-to-end in tests (`tests/test_api.py`).

## Status (Phase 4)

Implemented and tested end-to-end via `fastapi.testclient.TestClient`
(no live server, no network) - a project can be created, planned,
approved through both gates, and generated to `completed` purely over
HTTP. Route handlers currently call `SyncProjectOrchestrator` directly
(synchronous, in-process); a `TemporalProjectOrchestrator` swap (starting/
signaling the real `ProjectGenerationWorkflow`) is the production
upgrade path once a live Temporal server is available - see
`services/render-orchestrator/README.md`.
