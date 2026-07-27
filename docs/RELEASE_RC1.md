# Release Candidate 1

Snapshot of Sallehly AI Engine at the "Release Candidate" stage:
production-grade for the offline/local paths, code-complete but not
yet run against real GPU infrastructure for the RunPod path. This
document is the single entry point for anyone deciding whether to run
this release, and how - it doesn't replace `docs/PRODUCTION_READINESS_CHECKLIST.md`
(the detailed per-subsystem breakdown) or `docs/DECISIONS.md`/`docs/adr/`
(the design rationale); it summarizes them for a release decision.

## Current status

- **Core creative pipeline (Creative Director → Compiler → Cinematic
  Intelligence → post-production/export) - production-ready.** No open
  gaps; real end-to-end, real `apps/api` + `apps/web-dashboard`, real
  Playwright-driven browser flow, real `ffmpeg`.
- **Video generation - two of three modes production-ready.**
  `COMPUTE_PROVIDER=local` (mock, always was) and `local-inference`
  (real tiny-scale Wan generation, zero credentials) are both verified.
  `COMPUTE_PROVIDER=runpod` (real full-scale Wan2.2 on a real GPU) is
  code-complete, and its CI/CD deployment pipeline has run for real in
  free/dry-run mode - but no real, funded RunPod endpoint has been
  created yet. See "Deferred" below.
- **Wan2.2 LoRA training (Kaggle free-tier)** - production-ready,
  cost-protected, manually triggered only.
- **Security, error handling, logging, DB migrations, API contracts** -
  audited (read-only pass); no blockers found. The two concrete gaps
  the audit did find (migrations not automated on deploy, `/auth/refresh`
  undocumented) are both fixed as of this release.
- **Frontend UX** - functionally complete for the full project
  lifecycle; a handful of non-blocking polish items remain (no global
  Next.js error boundary, no automatic redirect-to-login on a token
  expiring mid-session) - tracked, not release-blocking.

## What's been verified

Everything below is a real, executed check in this environment, not a
claim - see `docs/PRODUCTION_READINESS_CHECKLIST.md` §0 for the full
evidence trail (run ids, commit hashes, exact commands):

- **Full backend test suite**: `uv run pytest tests/` - 757 passed, 28
  skipped (Redis/Temporal/real-GPU-only - each a real `importorskip`/
  env-gated skip, not a disabled test), `ruff check .` clean.
- **Frontend tests**: `apps/web-dashboard` - `npm test` (Vitest) 40/40
  passed; `npm run test:e2e` (Playwright, real `uvicorn` + `next dev`
  servers, no mocks) - full lifecycle suite passed, including reject-
  with-feedback, auth-required redirects, and per-user project isolation.
- **Local stack, browser-driven, end to end**: register → create
  project → generate creative plan → storyboard renders → approve →
  render plan renders → approve → generation completes → assets visible
  - confirmed with real screenshots, not just assertions.
- **GitHub Actions CI/CD, free mode**: `deploy-runpod-endpoint.yml` run
  [30231055452](https://github.com/Y1X0/sallehly-ai-engine/actions/runs/30231055452)
  completed with `conclusion: success` - real Docker build + push to
  GHCR, `deploy_endpoint.py --dry-run` validated the deploy logic
  without ever calling the real RunPod API, `verify-health` correctly
  skipped.
- **Alembic migration**: `alembic upgrade head` run for real against a
  fresh local Postgres 16 (via the new `apps/api/docker-entrypoint.sh`)
  - schema created from empty, idempotent on re-run, real `GET /healthz`
  200 after startup.
- **Security/error-handling/API-contract audit**: read-only review of
  ownership checks, rate limiting, input validation, secrets handling,
  exception handling, and `docs/api/openapi.yaml` vs. actual routes -
  no blockers; the two real gaps found are already fixed (see above).

## How to run it

**Fully offline, zero credentials** (the default - recommended for
evaluating the product itself):

```bash
cp .env.example .env
uv sync --all-packages
uv run --package api uvicorn api.main:app --app-dir apps/api/src --reload
# in a second terminal:
cd apps/web-dashboard && cp .env.local.example .env.local && npm install && npm run dev
# -> http://localhost:3000
```

This runs the entire creative pipeline plus real (tiny-scale) video
generation with `COMPUTE_PROVIDER=local-inference` - no GPU, no API
key, no external service. See `docs/DEV_SETUP.md` for the full guide,
including optional real Postgres/Redis/Temporal/S3 backends (each
independently opt-in, `memory`/`local` stays the default).

**Production deploy (Postgres-backed)**: set `PROJECT_STORE=postgres`
and a real `DATABASE_URL` - `apps/api/docker-entrypoint.sh` now runs
`alembic upgrade head` automatically before the server starts, no
manual migration step needed.

**Real RunPod GPU generation** (deferred - see below): follow
`infra/runpod/README.md`'s "Real RunPod deployment" section once a
funded RunPod account is available.

## Required variables

None are required for the default offline path (every setting below
has a safe default in `.env.example`). Only set what your deployment
mode actually needs:

| Variable | Needed for | Notes |
|---|---|---|
| `DATABASE_URL`, `PROJECT_STORE=postgres` | Real Postgres persistence | Migrations now run automatically on startup |
| `ANTHROPIC_API_KEY`, `LLM_PROVIDER=claude` | Real Claude-backed Creative Director | Defaults to a real, fully offline heuristic provider otherwise |
| `RUNPOD_API_KEY`, `RUNPOD_ENDPOINT_ID`, `COMPUTE_PROVIDER=runpod` | Real full-scale GPU video generation | `apps/api` fails fast at startup if either is missing - never silently falls back to the mock |
| `HF_TOKEN` | Only if the configured Wan2.2 HF repo becomes gated | Public as of this writing |
| `STORAGE_PROVIDER=s3`, `STORAGE_ENDPOINT_URL`, `STORAGE_ACCESS_KEY`, `STORAGE_SECRET_KEY` | Real S3/R2/MinIO storage | Defaults to local filesystem |
| `REDIS_URL`, `EVENT_BUS`/`TOKEN_STORE`/`CACHE_BACKEND`/`RATE_LIMITER`/`QUOTA_ENFORCER=redis` | Multi-replica deployments | Each independently opt-in, defaults to in-memory |
| `CORS_ALLOWED_ORIGINS` | Serving `apps/web-dashboard` from a non-default origin | Defaults to `http://localhost:3000` |
| `SENTRY_DSN`, `ERROR_REPORTER=sentry` | Real error tracking | Defaults to structured log output |

See `.env.example` for the complete, commented list.

## Deferred (explicitly out of scope for this release)

- **Real RunPod endpoint / real full-scale Wan2.2 GPU inference** - code
  and CI/CD automation complete and verified in dry-run mode; the one
  real attempt reached RunPod's actual API and was correctly rejected
  for lacking account balance (an account-funding step, not a code
  gap). Needs: a funded RunPod account, repository secrets, and one
  `real_deploy=true` workflow run - see `infra/runpod/README.md`.
- **GPU-dependent paths in general** - LoRA training execution beyond
  the orchestration-and-validation layer (`services/training/wan22`
  genuinely runs its full loop but has no attached real training
  backend by design - `IWan22TrainingBackend`'s only implementation
  raises `ModelUnavailableError` on purpose).
- **Real ML model adapters requiring GPU packages not installed here** -
  `IEmbeddingProvider` (CLIP/DINO), `IReferenceConditioningAdapter`
  (ControlNet/IP-Adapter beyond Canny edge detection), `IUpscaler` -
  interfaces and swap points are real and tested; concrete
  GPU-backed implementations are prepared, not shipped, by design
  (ADR 0013/0014).
- **`VastAIProvider`** - stub, `NotImplementedError` by design (Phase 3
  target, RunPod prioritized first per ADR 0005).
- **API versioning scheme** (`/v1/` or similar) - not yet addressed;
  no external consumers depend on the contract yet, so this is a
  documentation/planning gap, not a code gap.
- **Repository license** - open decision, flagged in `docs/DECISIONS.md`,
  intentionally left to a human call.
- **Frontend polish items** - no global Next.js error boundary, no
  automatic redirect-to-login on mid-session token expiry (both
  non-blocking, noted in the production audit).

## Versioning review

Root `pyproject.toml` currently reads `version = "1.0.0"` (set at the
previous "v1.0.0" checkpoint, tag created but not yet pushed to the
remote). **This number is not being changed by this document** - only
a recommendation, per the request that started this release-candidate
pass, for a human to decide on:

Semver's `1.0.0` signals a stable public API a consumer can already
depend on. That doesn't match this project's actual state: there is no
external consumer yet, no API versioning scheme, and the flagship
capability this platform exists to deliver - real full-scale Wan2.2
generation on real GPU infrastructure - has never completed a real run
(RunPod rejected the one real attempt for lacking account balance, see
"Deferred" above). Shipping `1.0.0` today would overclaim stability the
project doesn't yet have evidence for.

**Recommendation: `0.1.0`**, with this build tagged as a pre-release
(`0.1.0-rc.1`) until the real RunPod run in "Deferred" completes, at
which point `1.0.0` becomes an honest claim. `0.1.0` (not `0.9.0` or
similar) because nothing about this codebase has shipped to an external
consumer before - it's the first release, and semver's own convention
for "we don't yet promise API stability" is a `0.x` line, bumping the
minor version on breaking internal changes until a real `1.0.0` is
warranted. This is a recommendation only; `pyproject.toml`/`CHANGELOG.md`
are unchanged by this document.
