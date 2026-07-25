# Local Development Setup

## Prerequisites

- Python 3.11+
- [`uv`](https://github.com/astral-sh/uv) (workspace/package manager)
- Docker + Docker Compose
- Node.js 20+ and npm (only needed for `apps/web-dashboard`)
- `ffmpeg`/`ffprobe` on `PATH` (only needed for `services/post-processing`/
  `services/export-service`) - e.g. `apt-get install ffmpeg` on Debian/
  Ubuntu, `brew install ffmpeg` on macOS. Needs `libx264`/`libx265`/
  `libvpx`/`libopus`/`libmp3lame`/`libass` support (`ffmpeg -codecs`/
  `-filters` to check) - the standard Ubuntu/Homebrew builds have all of
  these. Without it, `post_processing.ffmpeg_utils.FfmpegNotAvailableError`
  is raised with a clear message, and the Phase 6 ffmpeg-execution tests
  are skipped rather than failing (see ADR 0012).
- Optional, only for real Cinematic Intelligence model adapters
  (`torch`, `open_clip_torch`, `torchvision`, `controlnet_aux`,
  `transformers` - none installed by default, none required to run the
  test suite or API): without them, `ClipEmbeddingProvider`/
  `DinoEmbeddingProvider.embed_image` and `IPAdapterConditioningAdapter.apply`
  raise `ModelUnavailableError` with the exact `pip install` command
  needed; `ControlNetConditioningAdapter`'s default canny preprocessing
  needs only Pillow, already a hard dependency (see ADR 0014).

## 1. Bootstrap

```bash
git clone <this repo>
cd sallehly-ai-video-engine
cp .env.example .env
uv sync   # installs the whole workspace (apps/*, services/*, packages/*)
```

## 2. Start local infrastructure

```bash
make up      # postgres, redis, minio (docker compose up -d)
```

Temporal's dev server is opt-in - two ways to run one:

```bash
# Option A: docker compose (needs the Docker daemon + network access to
# Docker Hub's registry, which some sandboxes/CI runners restrict)
docker compose --profile temporal up -d temporal

# Option B: the real temporal CLI directly - no Docker required, and
# genuinely what tests/test_temporal_orchestrator.py runs against
curl -sSL -o temporal-cli.tar.gz \
  "https://github.com/temporalio/cli/releases/download/v1.5.0/temporal_cli_1.5.0_linux_amd64.tar.gz"
tar xzf temporal-cli.tar.gz && sudo mv temporal /usr/local/bin/
temporal server start-dev --ip 127.0.0.1 --port 7233 --ui-port 8233
```

This runs a real Temporal server for `ProjectGenerationWorkflow`
(`services/render-orchestrator/src/render_orchestrator/workflows/`).
`apps/api`'s route handlers use `SyncProjectOrchestrator` by default (no
Temporal dependency, `ORCHESTRATOR=sync`) - set `ORCHESTRATOR=temporal`
to select `TemporalProjectOrchestrator` instead, then run a worker
process alongside the API:

```bash
ORCHESTRATOR=temporal uv run python -m api.temporal_worker
```

Genuinely executed as of Phase 8 WP6 - not just structurally validated
against the SDK's decorators as it was through Phase 4-7 - see
`docs/adr/0015-temporal-activation.md` for the workflow redesign this
required and `docs/adr/0010-persistence-and-lifecycle.md` for why both
`SyncProjectOrchestrator`/`TemporalProjectOrchestrator` exist and call
the same `ProjectLifecycle` methods underneath. One real limitation
today: every store `apps/api/state.py` wires is still in-memory (Phase
8 WP2 hasn't landed - see `docs/PHASE8_SCALEOUT_PLAN.md`), so the
worker and the API process only see the same project state if they
share one process - genuinely separate worker/API processes need WP2's
Postgres-backed stores first.

## 3. Run the API

```bash
uv run uvicorn api.main:app --reload
curl http://localhost:8000/healthz
```

By default (no `ANTHROPIC_API_KEY`/`RUNPOD_API_KEY` set) the API wires
itself to `LocalHeuristicLLMProvider` + `Wan21Adapter` + `LocalProvider`
(see `apps/api/src/api/state.py`) - fully offline, no GPU, no API key.
Every route except `/auth/register`/`/auth/login` requires a bearer
token (`packages/auth`) - register, log in, then drive a project through
its full lifecycle:

```bash
curl -sX POST localhost:8000/auth/register -H 'content-type: application/json' \
  -d '{"email": "dev@example.com", "password": "hunter22"}'

TOKEN=$(curl -sX POST localhost:8000/auth/login -H 'content-type: application/json' \
  -d '{"email": "dev@example.com", "password": "hunter22"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')

curl -sX POST localhost:8000/projects -H "authorization: Bearer $TOKEN" -H 'content-type: application/json' -d '{
  "prompt": "A 12-second warm premium product ad for a minimalist watch",
  "target_duration_sec": 12, "aspect_ratio": "16:9"
}'
# -> {"project_id": "proj_...", "status": "created", ...}  (workspace_id/created_by come from the token)

curl -sX POST -H "authorization: Bearer $TOKEN" localhost:8000/projects/<project_id>/generate-plan
curl -s -H "authorization: Bearer $TOKEN" localhost:8000/projects/<project_id>/storyboard
curl -sX POST -H "authorization: Bearer $TOKEN" localhost:8000/projects/<project_id>/approve-storyboard
curl -s -H "authorization: Bearer $TOKEN" localhost:8000/projects/<project_id>/render-plan
curl -sX POST -H "authorization: Bearer $TOKEN" localhost:8000/projects/<project_id>/approve-render
curl -sX POST -H "authorization: Bearer $TOKEN" localhost:8000/projects/<project_id>/generate-video
curl -s -H "authorization: Bearer $TOKEN" localhost:8000/projects/<project_id>/assets
```

See `docs/api/openapi.yaml` for the full contract, including
`reject-storyboard`/`reject-render` (rejects with feedback and
regenerates just that stage), `retry-generation`, `assets/upload`, and
`GET /jobs/{id}`/`GET /jobs/{id}/status`.

## 3b. Run the frontend

```bash
cd apps/web-dashboard
cp .env.local.example .env.local   # NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
npm install
npm run dev
# -> http://localhost:3000
```

Requires the API (step 3) running separately - the frontend makes real
HTTP requests to it, never mocks the backend. `apps/api` allows
`http://localhost:3000` via CORS by default
(`Settings.cors_allowed_origins`); change it if you serve the frontend
from a different origin.

## 3c. Post-production (services/post-processing / services/export-service)

Wired into `ProjectLifecycle.finalize_project` / `POST /projects/{id}/finalize`
as of ADR 0014 - once a project reaches `completed`, finalize it over
HTTP (`curl -X POST .../finalize`, or the "Finalize & export" button in
`apps/web-dashboard`) rather than calling the modules below directly.
Requires `ffmpeg`/`ffprobe` on `PATH` (see Prerequisites above); against
the default `LocalProvider` compute stack this will fail with a clean
409 (`LocalProvider` writes placeholder JSON, not real video bytes - a
pre-existing Phase 3 limitation, not new here) - it succeeds end-to-end
against real generated clips (RunPod/a real `IVideoEngine`). The modules
themselves are still directly usable for scripting/testing:

```python
from post_processing import TimelineBuilder, register_defaults
from post_processing.compositor import FfmpegCompositor, timeline_from_dict
from export_service import ExportService, AssetPackager
from asset_manager import AssetManager

register_defaults()  # built-in transition plugins -> TRANSITION_PLUGIN_REGISTRY
assets = AssetManager()

# director_plan: a DirectorPlan dict (e.g. from CreativeDirector.generate_director_plan)
# video_assets_by_shot_id: {shot_id: AssetRecord dict} for that project's generated clips
timeline_dict = TimelineBuilder().build(director_plan, video_assets_by_shot_id)
result = FfmpegCompositor(asset_manager=assets).compose(timeline_from_dict(timeline_dict), "master.mp4")

export = ExportService(assets).export(director_plan["project_id"], result.output_uri, {"format": "mp4", "quality_preset": "1080p"})
manifest = AssetPackager().package(director_plan["project_id"], export)
```

## 3d. Cinematic Intelligence Layer (services/cinematic-intelligence)

Wired into `ProjectLifecycle.approve_storyboard`/`reject_render_plan`
as of ADR 0014 - `CinematicIntelligenceCoordinator.enrich_render_plan`
runs automatically once a storyboard is approved, patching every
RenderSpec's `positive_prompt`/`negative_prompt` before a human reviews
the render plan at gate 2. Its live report/repair actions are available
over HTTP at `/projects/{id}/cinematic/*` (`analyze`, `report`,
`prompts/{shot_id}/improve`, `repair/{shot_id}`, `repairs`,
`repairs/{id}/approve|reject` - see `docs/api/openapi.yaml`) and in the
dashboard's Cinematic Intelligence panel. Still pure Python, no external
binary required - `CLIP`/`DINO`/`ControlNet`/`IP-Adapter` model adapters
(`services/cinematic-intelligence/model_adapters/`) are real where a
technique needs no trained model (Canny edge detection via Pillow,
already a hard dependency) and raise a clear `ModelUnavailableError`
everywhere else (`pip install torch open_clip_torch torchvision
controlnet_aux transformers` - none required to run the test suite or
API). The engines are still directly usable for scripting/testing:

```python
import cinematic_intelligence as ci

ci.register_defaults()  # prompt translators, quality metrics, repair strategies -> their registries

characters = ci.CharacterConsistencyEngine()
alice = characters.establish(
    "proj_1", "Alice",
    {"face_description": "oval face, freckles", "age_range": "adult", "skin_tone": "tan"},
)  # created once; every later shot calls characters.get("char_...") to reuse it, never re-establishes it

style_lock = ci.StyleLockEngine()
lock = style_lock.lock("proj_1", {"visual_style": "cinematic photorealistic"})

prompts = ci.PromptIntelligenceEngine()
package = prompts.build("proj_1", "shot_1", "Alice walks into the room", characters=[alice], style_lock=lock)
translated = prompts.translate(package, "wan2.1")  # -> RenderSpec.positive_prompt/negative_prompt

memory = ci.TemporalMemoryEngine()
memory.record_shot("proj_1", "shot_1", "scene_1", "Alice enters", character_ids=["char_alice"])

quality = ci.SceneQualityAnalyzer()
report = quality.analyze("proj_1", "shot_1", prompt_score=package["score"])
if report["repair_recommended"]:
    ci.AutomaticRepairEngine().repair(report, context={"current_positive_prompt": package["positive_prompt"]})
```

## 4. Exercise the pipeline without a GPU

Set `COMPUTE_PROVIDER=local` (the `.env.example` and `apps/api` default).
This routes render jobs through `LocalProvider`
(`services/video-engine-adapter/src/video_engine_adapter/compute/local_provider.py`),
which writes the job payload to `.docker-data/local-render-output/` and
reports success immediately — no GPU, no RunPod/Vast.ai account, no
network call. This is enough to build and test the entire pipeline (AI
Director → Compiler → GenerationPipeline → AssetManager → API) end to
end - see step 3 above.

To submit real Wan2.1 render jobs to RunPod instead, set:

```bash
COMPUTE_PROVIDER=runpod
RUNPOD_API_KEY=...
RUNPOD_ENDPOINT_ID=...
```

To switch which `IVideoEngine` handles generation - no code change,
`apps/api/state.py` reads this through `VIDEO_ENGINE_REGISTRY` (ADR 0014):

```bash
VIDEO_ENGINE=wan2.1     # default
VIDEO_ENGINE=sallehly-v1  # SallehlyModelAdapter - real capabilities(),
                           # but no trained weights yet (Phase 9), so
                           # every generation job fails with a clear
                           # SallehlyModelNotTrainedError - useful today
                           # only to prove the swap point is real
```

## 5. Running tests / lint

```bash
make test    # uv run pytest
make lint    # uv run ruff check .
make fmt     # uv run ruff format .
```

Tests in `test_ffmpeg_compositor.py`/`test_thumbnail_engine.py`/
`test_watermark_engine.py`/`test_export_service.py`/
`test_asset_packaging.py` actually run `ffmpeg` against real synthetic
clips (`tests/media_helpers.py`) - they `skip` (not fail) if `ffmpeg`
isn't installed.

Cinematic Intelligence Layer tests (`test_character_consistency.py`,
`test_object_consistency.py`, `test_environment_consistency.py`,
`test_scene_continuity.py`, `test_camera_continuity.py`,
`test_style_lock.py`, `test_reference_images.py`,
`test_prompt_intelligence.py`, `test_temporal_memory.py`,
`test_memory_graph.py`, `test_quality_analyzer.py`,
`test_repair_engine.py`) are pure Python - no `ffmpeg`, no network, no
model download - and always run. Check coverage on just this layer with:

```bash
uv run pytest tests/ -k "cinematic or consistency or continuity or style_lock or reference_images or prompt_intelligence or temporal_memory or memory_graph or quality_analyzer or repair_engine" \
  --cov=services/cinematic-intelligence/src/cinematic_intelligence \
  --cov=packages/cinematic-intelligence-sdk/src/cinematic_intelligence_sdk \
  --cov-report=term-missing
```

Frontend (`apps/web-dashboard`):

```bash
npm test          # vitest run - unit tests (design system, apiClient)
npm run lint       # eslint
npm run test:e2e   # playwright test - full lifecycle against real uvicorn/next dev servers
```

## 6. Adding a new workspace member

Any new `services/<name>` or `packages/<name>` directory with its own
`pyproject.toml` is picked up automatically by the root
`[tool.uv.workspace]` glob (`apps/*`, `services/*`, `packages/*`) — run
`uv sync` again after adding one.
