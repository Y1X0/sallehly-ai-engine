# Local Development Setup

## Prerequisites

- Python 3.11+
- [`uv`](https://github.com/astral-sh/uv) (workspace/package manager)
- Docker + Docker Compose
- Node.js 20+ and npm (only needed for `apps/web-dashboard`)

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

Temporal's dev server is opt-in:

```bash
docker compose --profile temporal up -d temporal
```

This runs a real Temporal server for `ProjectGenerationWorkflow`
(`services/render-orchestrator/src/render_orchestrator/workflows/`) - a
worker process (not included yet; run `temporalio`'s `Worker` with
`ProjectGenerationWorkflow` and `ProjectActivities(lifecycle).all_activities()`)
would connect to it via `temporalio.client.Client.connect("localhost:7233")`.
The API's route handlers use `SyncProjectOrchestrator` directly by
default (no Temporal dependency) - see
`docs/adr/0010-persistence-and-lifecycle.md` for why both paths exist and
call the same `ProjectLifecycle` methods underneath.

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

## 5. Running tests / lint

```bash
make test    # uv run pytest
make lint    # uv run ruff check .
make fmt     # uv run ruff format .
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
