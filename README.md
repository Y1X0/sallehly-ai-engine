# Sallehly AI Video Engine

An AI-directed cinematic video generation platform.

An LLM (Claude today, any provider tomorrow) acts purely as the **Creative
Director** — it understands a creative brief and produces a fully structured
production plan (storyboard, scenes, camera, lighting, motion, style). It
never generates pixels. A separate, swappable **Video Engine** layer
(Wan2.1 today, a custom foundation model later) executes that plan and
renders the actual video.

```
POST /projects  (apps/api)
   -> ProjectLifecycle: Creative Planning
        -> AI Director (LLM layer, provider-agnostic)
        -> Creative Compiler (Style / Camera / Motion / Lighting -> Storyboard)
   -> [approval gate 1: storyboard]  (WAITING_STORYBOARD_APPROVAL)
        -> Render Specification Generator (engine-agnostic RenderPlan)
   -> [approval gate 2: render plan]  (WAITING_RENDER_APPROVAL)
   -> Cinematic Intelligence Layer (Character/Object/Environment/Style memory -> PromptPackage)
   -> Video Engine Adapter (Wan2.1) + Compute Provider (RunPod / local)
   -> GenerationJob (queued -> running -> completed/failed) + AssetManager
        -> Scene Quality Analyzer -> Automatic Repair Engine (per-shot, as needed)
   -> Timeline Builder -> Transition Engine / Audio Pipeline / Subtitle System / Watermark Engine
   -> FfmpegCompositor (master video) -> Export Service (mp4/mov/webm x 720p-4K) -> RenderManifest
```

A user drives this whole flow from a real browser
(`apps/web-dashboard`), never by calling `apps/api` directly.

Driven synchronously (`SyncProjectOrchestrator`) today, or by a durable
`ProjectGenerationWorkflow` (Temporal) in production - same
`ProjectLifecycle` either way.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full system
design, [`docs/DECISIONS.md`](docs/DECISIONS.md) for the decision log, and
[`docs/adr/`](docs/adr/) for individual Architecture Decision Records.

## Status

**Phase 8 — Pipeline integration.** A user can register, submit a
creative idea, review and approve/reject the storyboard and render
plan, watch it through to a generated video asset, review a live
Cinematic Intelligence report (consistency scores, detected problems,
one-click repair approve/reject) and finalize the project into one
exported deliverable — entirely from a real browser UI, which talks to
`apps/api` and nothing else. Every project's per-shot clips can be
stitched, mixed, subtitled, watermarked, and exported by a real,
ffmpeg-executable post-production pipeline, and a rule-based Cinematic
Intelligence Layer keeps a project's characters/objects/environments/
style/camera consistent shot to shot - both are now wired directly into
`ProjectLifecycle`/`apps/api`/`apps/web-dashboard` (see Phase 8 below;
Phase 6/7 below describe when each was originally built):

- **Phase 1** (`services/ai-director`, `CreativeDirector`): Creative
  Brief Parser → Story Planner (LLM-backed) → Scene Generator → Shot
  Planner (deterministic) → `DirectorPlan`.
- **Phase 2** (`services/creative-compiler`, `CreativeCompiler`): Style →
  Camera → Motion → Lighting Directors (deterministic) → Storyboard
  Generator → **approval gate 1** → Render Specification Generator →
  **approval gate 2** → `RenderPlan`.
- **Phase 3** (`services/video-engine-adapter`, `services/render-orchestrator`,
  `services/asset-manager`): `Wan21Adapter` + production `RunPodProvider`
  (real HTTP client, retry-with-backoff) → `GenerationPipeline` tracking
  each shot as a `GenerationJob` → `AssetManager`. `CreativeDirector`/
  `CreativeCompiler` remain unaware any of this exists.
- **Phase 4** (`services/render-orchestrator`, `packages/persistence`,
  `apps/api`): `ProjectLifecycle` — the single implementation of
  `Project Created → Creative Planning → Storyboard Gate → Render Gate →
  Generation → Asset Processing → Completion`, including reject-with-
  feedback/regenerate on both gates — driven synchronously today
  (`SyncProjectOrchestrator`) or, in production, by a real
  `ProjectGenerationWorkflow` (Temporal: durable, resumes after a crash).
  `apps/api` exposes the full endpoint surface
  (`POST /projects`, `.../generate-plan`, `.../approve-storyboard`,
  `.../approve-render`, `.../generate-video`, `GET /jobs/{id}`,
  `GET /projects/{id}/assets`, ...), tested end-to-end via
  `TestClient` against a fully offline default stack
  (`LocalHeuristicLLMProvider` + `Wan21Adapter` + `LocalProvider` — no
  API key, no GPU, no network).
- **Phase 5** (`packages/auth`, `apps/api`, `apps/web-dashboard`):
  provider-independent auth (`IAuthProvider`, PBKDF2 + bearer tokens,
  personal workspace per user) with ownership checks on every
  project-scoped route; new `GET /projects` (list), `GET
  /projects/{id}/{plan,storyboard,render-plan}` (review content the
  frontend needs — a real gap Phase 4 left, found while building the
  frontend against the existing contract), `POST
  /projects/{id}/retry-generation`, `POST /assets/upload`, and CORS
  (another real gap, only visible once a real browser exercised the
  API instead of `TestClient`). `apps/web-dashboard` (Next.js App
  Router + TypeScript + Tailwind): login/register, project dashboard,
  creative workspace (lifecycle timeline, story/scene/shot cards,
  storyboard/render-plan approval panels, real-time job status with
  retry, asset library) — tested with Vitest (unit) and Playwright
  (real Chromium, full lifecycle e2e, against real `uvicorn`/`next dev`
  servers).
- **Phase 6** (`packages/video-composition-sdk`,
  `services/post-processing`, `services/export-service`): `Timeline
  Builder` sequences a project's shots (honoring
  `Shot.transition_in`/`transition_out`) into a `Timeline`; the
  `Transition Engine` resolves cinematic-cut/fade-in/fade-out/dissolve/
  match-cut/wipe/whip-pan/zoom (plus custom plugins) via a real registry
  (`TRANSITION_PLUGIN_REGISTRY`); the `Audio Pipeline` mixes music/sfx/
  voiceover tracks with volume automation; the `Subtitle System`
  generates real SRT/WebVTT (or burns captions in) with styling presets
  and multilingual tracks; the `Thumbnail Engine` extracts real
  keyframes; the `Watermark Engine` handles logo overlay and intro/outro;
  `FfmpegCompositor` assembles all of it into one master video; the
  `Export Service` re-encodes to mp4/mov/webm at 720p/1080p/1440p/4K;
  `AssetPackager` bundles everything into a `RenderManifest`. **Every
  one of these actually runs `ffmpeg`** against real synthetic clips in
  its tests (`tests/media_helpers.py`) rather than being mocked - the
  first layer in this codebase held to that bar, since (unlike GPU
  inference or a live Temporal server) `ffmpeg` is a real, installable,
  executable dependency here. `IUpscaler`/`PassthroughUpscaler` is the
  one honest exception: prepared per Phase 6's explicit scope, not
  implemented, since real upscaling needs a GPU model deployment. As of
  Phase 8, wired into `ProjectLifecycle.finalize_project` /
  `POST /projects/{id}/finalize`.
- **Phase 7** (`packages/cinematic-intelligence-sdk`,
  `services/cinematic-intelligence`): sits between the Render
  Specification Generator and the Video Engine Adapter. The
  `Character`/`Object`/`Environment Consistency Engines` create
  immutable `CharacterIdentityProfile`s (reused, never regenerated) and
  track evolving object/environment state; the `Scene`/`Camera
  Continuity Engines` diff adjacent shots' entry/exit points, eye
  lines, actor positions, motion direction, timing, lens, height, and
  movement into a `ContinuityReport`; the `Style Lock Engine` locks one
  global look per project and flags drift; the `Reference Image
  Engine` builds reusable reference packages; the `Prompt Intelligence
  Engine` builds every shot's prompt from that memory (never a raw
  prompt) with a real `PromptOptimizer`/`NegativePromptBuilder`/
  `PromptCompressor`/`PromptScorer`/`PromptVersioning` and
  `IPromptTranslator` plugins for wan2.1/veo/runway/luma/kling/pika;
  the `Temporal Memory Engine` maintains one `ProjectMemory` per
  project, updated after every shot; the `Director Memory Graph`
  builds a real (in-memory today, Neo4j-shaped) node/edge graph; the
  `Scene Quality Analyzer` scores each shot from that same continuity/
  style/prompt data via pluggable `IQualityMetric`s; the `Automatic
  Repair Engine` routes a shot's worst-scoring dimension to a matching
  `IRepairStrategy`, always scoped to that one shot. Every extension
  point (`IPromptTranslator`, `IQualityMetric`, `IRepairStrategy`) is a
  real `config_sdk.Registry`, the same plugin mechanism Phase 6
  established. **Two interfaces are prepared, not implemented:**
  `IEmbeddingProvider` (CLIP/DINO perceptual scoring) and
  `IReferenceConditioningAdapter` (ControlNet/IP-Adapter generation-time
  conditioning) both need a deployed vision model this sandbox doesn't
  have, and the phase explicitly forbade training one - every
  consistency/quality signal here is genuinely computed from structured
  metadata, not pixels. ≥95% test coverage on every new module.
- **Phase 8** (`services/cinematic-intelligence` `coordinator.py` +
  `model_adapters/`, `services/render-orchestrator`, `apps/api`,
  `apps/web-dashboard` - see `docs/adr/0014-pipeline-integration.md`):
  `CinematicIntelligenceCoordinator` wires all ten Phase 7 engines into
  `ProjectLifecycle.approve_storyboard`/`reject_render_plan`, patching
  every `RenderSpec`'s prompts and recording continuity/quality data
  before a human ever reviews the render plan; a new
  `ProjectLifecycle.finalize_project` (`completed` → `post_processing`
  → `exported`) hands the project's generated clips to
  `PostProductionRunner`, reusing the entire Phase 6 pipeline unchanged.
  `apps/api` gains `/projects/{id}/cinematic/*` (analyze/report/improve-
  prompt/repair/approve/reject) and `/finalize`+`/render-manifest`;
  `apps/web-dashboard` gains a Cinematic Intelligence panel (scores,
  problems, repair approve/reject) and a finalize/download flow.
  `IEmbeddingProvider`/`IReferenceConditioningAdapter` (prepared, not
  implemented, in Phase 7) now have concrete adapters
  (`ClipEmbeddingProvider`/`DinoEmbeddingProvider`/
  `ControlNetConditioningAdapter`/`IPAdapterConditioningAdapter`): real
  where a technique needs no trained model (cosine similarity, Canny
  edge detection via Pillow), a clear `ModelUnavailableError` everywhere
  else (`torch`/`open_clip`/`torchvision`/`controlnet_aux`/
  `transformers`, none installed here). A real gap surfaced and fixed
  along the way: `apps/api` had imported `Wan21Adapter` directly since
  Phase 4 and never actually read the `VIDEO_ENGINE_REGISTRY`/
  `Settings.video_engine` config switch that already existed -
  `SallehlyModelAdapter`, a second real `IVideoEngine` (registered as
  `sallehly-v1`, real `capabilities()`, correctly raises
  `SallehlyModelNotTrainedError` since Phase 9 hasn't produced weights
  yet), proves the swap now genuinely works via config alone.
- **Phase 8 Scale-out WP6** (`services/render-orchestrator/workflows`,
  `apps/api` - see `docs/adr/0015-temporal-activation.md`):
  `ProjectGenerationWorkflow` redesigned from auto-chained signals to
  one real `@workflow.update` per `IProjectOrchestrator` method; the new
  `TemporalProjectOrchestrator` and `build_worker()` are genuinely
  executed - not just structurally validated - against a real `temporal`
  CLI dev server (`tests/test_temporal_orchestrator.py`, including a
  worker-restart durability test). `ORCHESTRATOR=temporal` selects it
  alongside the default `sync` driver, zero route-handler changes in
  `apps/api`.
- **Phase 8 Scale-out WP2** (`packages/persistence` - see
  `docs/adr/0016-postgres-persistence.md`): `PostgresProjectStore`, a
  second real `IProjectStore` implementation (SQLAlchemy Core,
  `SELECT ... FOR UPDATE` row locking against concurrent writers), is
  genuinely executed - not just structurally validated - against a real
  local Postgres 16 server (`tests/test_postgres_project_store.py`), with
  a real, applied Alembic migration (`packages/persistence/alembic`).
  `PROJECT_STORE=postgres` selects it alongside the default `memory`
  driver, zero call-site changes anywhere above `IProjectStore`.
- **Phase 8 Scale-out WP3** (`packages/cache-sdk` (new),
  `services/render-orchestrator/redis_event_bus.py`, `packages/auth` -
  see `docs/adr/0017-redis-backed-infra.md`): a new `ICache`
  (`InMemoryCache`/`RedisCache`), `RedisEventBus(IEventBus)`, and
  `ITokenStore`/`RedisTokenStore` (extracted from `LocalAuthProvider`'s
  previously-internal token dict) are all genuinely executed - not just
  structurally validated - against a real local Redis 7 server
  (`tests/test_cache_sdk.py`, `tests/test_redis_event_bus.py`,
  `tests/test_redis_token_store.py`, including cross-instance delivery
  simulating separate API/worker processes). `CACHE_BACKEND`/
  `EVENT_BUS`/`TOKEN_STORE=redis` each independently select the Redis
  implementation alongside the default `memory` one.
- **Phase 8 Scale-out WP4** (`packages/storage-sdk` - see
  `docs/adr/0018-s3-storage-provider.md`): `S3Provider(IStorageProvider)`
  via `boto3`. A live MinIO/S3 endpoint is unreachable in this sandbox
  (both `docker pull minio/minio` and a direct `dl.min.io` binary
  download are blocked by the egress policy, with no GitHub-Releases-style
  unblocked alternative the way Temporal had) - tested instead against
  `moto`'s `ThreadedMotoServer`, a real, separately-running HTTP server
  implementing the genuine S3 REST API (`tests/test_s3_provider.py`,
  including a read-back through an independently-constructed `boto3`
  client to prove the round trip is real). `STORAGE_PROVIDER=s3` selects
  it alongside the default `local` filesystem driver. Documented
  honestly as a different rigor tier than WP2/WP3's exact-backend tests
  - see the ADR's Consequences.

One thing remains genuinely unexecuted in this environment, documented
rather than glossed over: real GPU inference (`workers/gpu-worker` needs
actual Wan2.1 weights deployed to a GPU). Everything on the code side of
that boundary is implemented and tested against local/mocked
equivalents - the same honesty class Phase 8 held its own two
genuinely-vision-model-dependent interfaces to. Live Temporal execution
- long documented as the other side of this same boundary (ADR 0010) -
turned out to be narrower than that: a real `temporal` CLI dev server
(downloaded directly from GitHub Releases, not through the SDK's own
blocked auto-downloader) runs here, and `ProjectGenerationWorkflow`/
`TemporalProjectOrchestrator` are genuinely executed against it as of
Phase 8 WP6 (`docs/adr/0015-temporal-activation.md`) - `ORCHESTRATOR=temporal`
is a real, tested `IProjectOrchestrator` alongside the default `sync`
driver. See the roadmap in `docs/ARCHITECTURE.md#8-roadmap`.

## Repository layout

| Path | Purpose |
|---|---|
| `apps/` | User-facing applications (web dashboard, public API gateway) |
| `services/` | Independently deployable backend services — one per pipeline stage |
| `packages/` | Shared libraries: contracts (`schemas`), provider interfaces (`llm-providers`, `video-engine-sdk`, `storage-sdk`), persistence (`persistence`), cross-cutting utilities |
| `libraries/` | Content, not code: prompt fragments and DirectorPlan templates |
| `plugins/` | Registered extensions: LLM providers, video engines, post-fx filters |
| `workers/` | GPU-side execution containers (what actually runs on rented GPUs) |
| `infra/` | Docker, Kubernetes (future), RunPod/Vast.ai deployment config, Terraform (future) |
| `models/` | Model registry and per-engine capability manifests |
| `configs/` | Per-environment configuration |
| `docs/` | Architecture, ADRs, API contracts, module docs |

Each `services/*` and `packages/*` directory has its own `README.md`
explaining its responsibility, inputs/outputs, and the interfaces it
implements or consumes.

## Local development

See [`docs/DEV_SETUP.md`](docs/DEV_SETUP.md).

```bash
cp .env.example .env
docker compose up -d
```

## Core architectural rule

The LLM layer and the Video Engine layer never call each other directly.
They only exchange structured, versioned JSON that conforms to the schemas
in `packages/schemas/json/`. This is what allows either side to be replaced
without rewriting the rest of the system — see
[`docs/adr/0001-director-engine-separation.md`](docs/adr/0001-director-engine-separation.md).
