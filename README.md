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
   -> Video Engine Adapter (Wan2.1) + Compute Provider (RunPod / local)
   -> GenerationJob (queued -> running -> completed/failed) + AssetManager
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

**Phase 6 — Post-production pipeline.** A user can register, submit a
creative idea, review and approve/reject the storyboard and render plan,
and watch it through to a generated video asset — entirely from a real
browser UI, which talks to `apps/api` and nothing else — and every
project's per-shot clips can be stitched, mixed, subtitled, watermarked,
and exported to a final deliverable by a real, ffmpeg-executable
post-production pipeline (not yet wired into the API/frontend - see
Phase 6 below):

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
  implemented, since real upscaling needs a GPU model deployment.

Two things remain genuinely unexecuted in this environment, both
documented rather than glossed over: real GPU inference (`workers/gpu-worker`
needs actual Wan2.1 weights deployed to a GPU) and live Temporal
execution (its ephemeral test server needs a binary download this
sandbox's network policy blocks). Everything on the code side of both
boundaries is implemented and tested against local/mocked equivalents.
See the roadmap in `docs/ARCHITECTURE.md#8-roadmap`.

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
