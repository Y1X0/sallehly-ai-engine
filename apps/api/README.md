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
| `POST /auth/register` | `auth_provider.register` |
| `POST /auth/login` | `auth_provider.authenticate` |
| `GET /users/me` | `auth_provider.verify_token` (via `get_current_user`) |
| `GET /projects` | `project_store.list_for_workspace(current_user.workspace_id)` |
| `POST /projects` | `orchestrator.create_project` (`workspace_id`/`created_by` from the token, not the request body) |
| `GET /projects/{id}` | `project_store.get` |
| `POST /projects/{id}/generate-plan` | `orchestrator.generate_creative_plan` |
| `GET /projects/{id}/plan` | `memory.latest(id, "director_plan_enriched" \| "director_plan")` - for the story editor/scene timeline/shot cards |
| `GET /projects/{id}/storyboard` | `memory.latest(id, "storyboard")` - for gate-1 review |
| `GET /projects/{id}/render-plan` | `memory.latest(id, "render_plan")` - for gate-2 review |
| `POST /projects/{id}/approve-storyboard` | `orchestrator.approve_storyboard` |
| `POST /projects/{id}/reject-storyboard` | `orchestrator.reject_storyboard` (regenerates the storyboard using the feedback) |
| `POST /projects/{id}/approve-render` | `orchestrator.approve_render_plan` |
| `POST /projects/{id}/reject-render` | `orchestrator.reject_render_plan` (recompiles the render plan, optionally with a new `quality_tier`) |
| `POST /projects/{id}/generate-video` | `orchestrator.generate_video` |
| `POST /projects/{id}/retry-generation` | `orchestrator.retry_generation` (requires status=`failed`) |
| `POST /projects/{id}/finalize` | `orchestrator.finalize_project` (requires status=`completed`; assembles the exported deliverable via `PostProductionRunner` - Phase 8) |
| `GET /projects/{id}/render-manifest` | `record.render_manifest` (`404` until finalized) |
| `POST /projects/{id}/cinematic/analyze` | `cinematic_intelligence.get_project_report` (live aggregation - Phase 8) |
| `GET /projects/{id}/cinematic/report` | Read-only alias for `.../analyze` |
| `POST /projects/{id}/cinematic/prompts/{shot_id}/improve` | `cinematic_intelligence.improve_prompt` |
| `POST /projects/{id}/cinematic/repair/{shot_id}` | `cinematic_intelligence.repair_shot` (requires a QualityReport for the shot) |
| `GET /projects/{id}/cinematic/repairs` | `cinematic_intelligence.list_repairs` |
| `POST /projects/{id}/cinematic/repairs/{repair_id}/approve` \| `.../reject` | `cinematic_intelligence.review_repair` |
| `GET /projects/{id}/assets` | `asset_manager.get` for each of the project's `asset_ids` |
| `POST /assets/upload` | `asset_manager.persist_local_copy` + `asset_manager.register` (multipart file upload, e.g. reference images) |
| `GET /jobs/{id}` | `job_store.get` |
| `GET /jobs/{id}/status` | `job_store.get` (status/retry_count/error_message only) |

Every route except `/auth/register` and `/auth/login` requires
`Authorization: Bearer <token>` (`get_current_user`, `401` if
missing/invalid). Every project-scoped route also checks
`record.created_by == current_user.user_id` (`403` otherwise) - see
`packages/auth`.

A `409` is returned when a request doesn't match the project's current
`ProjectStatus` (e.g. approving a storyboard that isn't
`waiting_storyboard_approval`) - see `ProjectLifecycleError`.

## Wiring (`state.py`)

`build_app_state()` runs once at startup (FastAPI `lifespan`) and is the
**only** place that reads `LLM_PROVIDER`/`COMPUTE_PROVIDER`/`VIDEO_ENGINE`
config and picks a concrete `ILLMProvider`/`IVideoEngine`/`IComputeProvider`.
In this environment (and by default anywhere `ANTHROPIC_API_KEY`/
`RUNPOD_API_KEY` aren't set), that resolves to `LocalHeuristicLLMProvider`
+ `Wan21Adapter` + `LocalProvider` - fully offline, no GPU, no API key,
which is what lets this API be exercised end-to-end in tests
(`tests/test_api.py`). `VIDEO_ENGINE` genuinely selects the engine via
`VIDEO_ENGINE_REGISTRY.create(...)` as of Phase 8 - this module used to
hardcode `Wan21Adapter()` directly and never actually read the config
value, a real gap found and fixed while implementing config-driven engine
swapping (`docs/adr/0014-pipeline-integration.md`). `build_app_state()`
also constructs a `CinematicIntelligenceCoordinator` and a
`PostProductionRunner`, injected into `ProjectLifecycle` unconditionally
(unlike `tests/conftest.py`'s `build_stack()`, which opts each in via a
flag).

## Status (Phase 4, extended Phase 8)

Implemented and tested end-to-end via `fastapi.testclient.TestClient`
(no live server, no network) - a project can be created, planned,
approved through both gates, generated to `completed`, and finalized to
`exported` purely over HTTP, with a live Cinematic Intelligence report
and repair workflow available throughout. Route handlers currently call
`SyncProjectOrchestrator` directly (synchronous, in-process); a
`TemporalProjectOrchestrator` swap (starting/signaling the real
`ProjectGenerationWorkflow`) is the production upgrade path once a live
Temporal server is available - see `services/render-orchestrator/README.md`.
