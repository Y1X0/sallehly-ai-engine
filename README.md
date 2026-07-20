# Sallehly AI Video Engine

An AI-directed cinematic video generation platform.

An LLM (Claude today, any provider tomorrow) acts purely as the **Creative
Director** — it understands a creative brief and produces a fully structured
production plan (storyboard, scenes, camera, lighting, motion, style). It
never generates pixels. A separate, swappable **Video Engine** layer
(Wan2.1 today, a custom foundation model later) executes that plan and
renders the actual video.

```
User Brief
   -> AI Director (LLM layer, provider-agnostic)
   -> Creative Compiler (Scene / Storyboard / Camera / Motion / Lighting / Style)
   -> Render Configuration (engine-agnostic RenderSpec)
   -> Video Engine Adapter (Wan2.1 today)
   -> Compute Provider (RunPod / Vast.ai today, Kubernetes later)
   -> Post-Processing
   -> Final MP4
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full system
design, [`docs/DECISIONS.md`](docs/DECISIONS.md) for the decision log, and
[`docs/adr/`](docs/adr/) for individual Architecture Decision Records.

## Status

**Phase 0 — Foundation.** This repository currently contains architecture,
contracts (JSON Schemas, API spec), interface definitions, and scaffolding
only. No product features are implemented yet. See the roadmap in
`docs/ARCHITECTURE.md#roadmap`.

## Repository layout

| Path | Purpose |
|---|---|
| `apps/` | User-facing applications (web dashboard, public API gateway) |
| `services/` | Independently deployable backend services — one per pipeline stage |
| `packages/` | Shared libraries: contracts (`schemas`), provider interfaces (`llm-providers`, `video-engine-sdk`), cross-cutting utilities |
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
