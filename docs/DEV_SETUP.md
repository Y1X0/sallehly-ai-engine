# Local Development Setup

## Prerequisites

- Python 3.11+
- [`uv`](https://github.com/astral-sh/uv) (workspace/package manager)
- Docker + Docker Compose

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

Temporal's dev server is opt-in (only needed once Phase 4 work begins):

```bash
docker compose --profile temporal up -d temporal
```

## 3. Run the API

```bash
uv run uvicorn api.main:app --reload --app-dir apps/api/src
curl http://localhost:8000/healthz
```

## 4. Exercise the pipeline without a GPU

Set `COMPUTE_PROVIDER=local` (the `.env.example` default). This routes
render jobs through `LocalProvider`
(`services/video-engine-adapter/src/video_engine_adapter/compute/local_provider.py`),
which writes the job payload to `.docker-data/local-render-output/` and
reports success immediately — no GPU, no RunPod/Vast.ai account, no
network call. This is enough to build and test every stage of the
pipeline (AI Director → Compiler → Orchestrator → "render" → Post-
Processing wiring) before Phase 3's real Wan2.1 integration exists.

To test against real Wan2.1 rendering once Phase 3 lands, set:

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

## 6. Adding a new workspace member

Any new `services/<name>` or `packages/<name>` directory with its own
`pyproject.toml` is picked up automatically by the root
`[tool.uv.workspace]` glob (`apps/*`, `services/*`, `packages/*`) — run
`uv sync` again after adding one.
