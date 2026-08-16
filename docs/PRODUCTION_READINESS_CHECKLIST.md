# Production Readiness Checklist — v1.0.0

Status of every major subsystem as of the v1.0.0 release, what's
actually verified vs. what still needs a human with real credentials,
and the exact manual steps left before this platform serves real
production traffic. Every ✅/⚠️ below is backed by a real, passing test
or a real (if sandbox-network-limited) execution - see the linked ADR
for the specific evidence, not just the claim.

## 0. Verification log (stabilization pass before further expansion)

A deliberate pause to confirm everything built so far actually runs,
before adding anything new, real deploy included:

- **Local stack e2e verified ✅** - `docker compose up -d postgres redis`
  itself is blocked by this sandbox's network policy (same CDN
  restriction as Docker Hub/RunPod, see §2/§6), but the app's own
  defaults (`PROJECT_STORE=memory`, `CACHE_BACKEND=memory`,
  `EVENT_BUS=memory`, `TOKEN_STORE=memory`, `STORAGE_PROVIDER=local`)
  need no external service at all. Ran `apps/api`
  (`uv run --package api uvicorn api.main:app`) and `apps/web-dashboard`
  (`npm run dev`) as real, separate OS processes and drove the full
  `e2e/lifecycle.spec.ts` Playwright suite against them (4/4 passed),
  plus a manual screenshot pass through every gate.
- **Browser lifecycle verified ✅** - register → log in → create project
  → generate creative plan → storyboard renders → approve → render plan
  renders → approve → start generation → generation completes → assets
  visible, all confirmed with real screenshots taken mid-run, not just
  the automated assertions. Reject-with-feedback, auth-required
  redirects, and per-user project isolation also passed.
- **GitHub Actions free mode verified ✅** - `deploy-runpod-endpoint.yml`
  run [30231055452](https://github.com/Y1X0/sallehly-ai-engine/actions/runs/30231055452)
  (`confirm_deploy=true`, `real_deploy=false`) completed with
  `conclusion: success`: `build-and-push` built and pushed a real image
  to GHCR, `deploy-endpoint` ran `deploy_endpoint.py --dry-run` (no
  `RUNPOD_API_KEY`, no Environment approval wait - `runpod-free-dry-run`
  has no protection rules), and `verify-health` was skipped entirely, as
  designed.
- **RunPod dry-run verified ✅** - same run: the "Free mode - validate
  deploy logic" step printed `Dry run OK ... Endpoint created:
  dry-run-noop` without ever calling `runpod.api_key`/
  `create_template()`/`create_endpoint()`. No RunPod account, balance,
  or credential was touched.

Nothing above used `real_deploy=true`, a real RunPod endpoint, or any
GPU deployment - see §2 and §6 for what remains genuinely unverified
(a real, funded RunPod run) and exactly why.

## 0b. Production audit - fixes applied

A read-only audit (security, error handling, logging, DB migration
readiness, API contracts, frontend UX) found the core pipeline,
ownership checks, rate limiting, input validation, and error handling
already production-ready with no blockers. Two concrete, high-priority
gaps were found and fixed here (no new features, no architecture
change, no RunPod/GPU involved):

- **Alembic migration now runs automatically on deploy ✅** -
  `apps/api/Dockerfile` previously started `uvicorn` directly with no
  migration step anywhere in the deploy path (`alembic upgrade head`
  was a manual local-only step per `docs/DEV_SETUP.md`); a real
  production deploy against Postgres risked running application code
  against an un-migrated schema. `apps/api/docker-entrypoint.sh` now
  runs `alembic upgrade head` before starting the server, gated on
  `PROJECT_STORE=postgres` (a no-op for the default `PROJECT_STORE=memory`,
  same swap-point discipline as every other `Settings`-driven default -
  see `docs/DECISIONS.md` decision 62), and still respects a `command:`
  override (e.g. `docker-compose.yml`'s `--reload` for local dev)
  instead of ignoring it. Verified for real against a fresh local
  Postgres 16: `alembic upgrade head` created the `projects`/
  `alembic_version` tables from empty, a second run was a clean no-op
  (idempotent), and the full entrypoint script (migration + real
  `uvicorn` startup) answered a real `GET /healthz` with `200 OK`.
- **`POST /auth/refresh` now documented ✅** - implemented in
  `apps/api/src/api/routes/auth.py` (token rotation, `docs/DECISIONS.md`
  decision 77) but entirely missing from `docs/api/openapi.yaml`.
  Added with the same request/response/security shape every other
  bearer-authenticated route uses. `docs/api/openapi.yaml` now lists
  all 29 real routes with none missing either direction.

Verified with the full suite after both changes: `uv run pytest tests/`
- 757 passed, 28 skipped (Redis/Temporal/real-GPU-only, same class of
skip as always), `ruff check .` clean, `apps/web-dashboard`'s
`npm test` - 40/40 passed.

## 1. Core creative pipeline

| Component | Status | Evidence |
|---|---|---|
| Creative Director (brief → story → scenes → shots) | ✅ Ready | `tests/test_creative_pipeline.py`, offline `LocalHeuristicLLMProvider` default |
| Creative Compiler (storyboard → render plan, both approval gates) | ✅ Ready | `tests/test_project_lifecycle.py` |
| Cinematic Intelligence (consistency, quality scoring, auto-repair) | ✅ Ready | Phase 7/8, ADR 0014 |
| Post-processing (timeline, transitions, audio, subtitles, export) | ✅ Ready | Real `ffmpeg` in every test, `tests/media_helpers.py` |
| `apps/api` (full REST surface, auth, ownership checks) | ✅ Ready | `tests/test_api.py`, 400+ endpoint-level tests |
| `apps/web-dashboard` | ✅ Ready | Vitest + Playwright e2e against real `uvicorn`/`next dev` |

No open gaps in this layer. This is the same pipeline audited and
shipped through Phase 8 Scale-out.

## 2. Video generation backends (`COMPUTE_PROVIDER`)

| Mode | Real or mock | Credentials | Status |
|---|---|---|---|
| `local` (default) | Mock stub (`LocalProvider`) | none | ✅ Ready - dev/CI default, always was |
| `local-inference` | **Real**, tiny-scale `WanPipeline` (`LocalInferenceProvider`) | none | ✅ Ready - verified end-to-end via headless browser, real playable `.mp4` produced |
| `runpod` | **Real**, full-scale Wan2.2 on a real GPU (`RunPodProvider` + `workers/gpu-worker`) | `RUNPOD_API_KEY`, `RUNPOD_ENDPOINT_ID`, `HF_TOKEN` (worker-side, only if the repo is gated) | ⚠️ Code + CI deployment automation (`.github/workflows/deploy-runpod-endpoint.yml`) complete; **build-and-push and the free/dry-run deploy path have both run for real and succeeded** (free-mode run [30231055452](https://github.com/Y1X0/sallehly-ai-engine/actions/runs/30231055452) - see §0); a real (`real_deploy=true`) endpoint has not been created - the one attempt (run 30228235422) reached the real RunPod API and was correctly rejected for lacking $0.01 account balance, an account-funding step, not a code gap - see §6 |
| `vastai` | Not implemented | — | ❌ Phase 3 target, unchanged, `VastAIProvider` raises `NotImplementedError` by design |

`build_app_state()` refuses to start with `COMPUTE_PROVIDER=runpod` and
incomplete credentials - confirmed by `tests/test_api_state_compute_provider.py`.
Never silently degrades to the mock.

## 3. Wan2.2 LoRA training pipeline

| Component | Status | Evidence |
|---|---|---|
| Real training backend (`Wan22DiffusersBackend`) | ✅ Ready | Real `diffusers`/`peft` forward/backward/optimizer step, `tests/test_training_wan22_diffusers_backend.py` |
| HF weight download + checksum verification | ✅ Ready | `training.hf_download`, real per-file SHA-256, never random weights |
| Dataset ingestion (real ffprobe, validation, versioning) | ✅ Ready | Phase 9 Preparation |
| Kaggle free-GPU dispatch | ✅ Ready | Real `kaggle` CLI wrapper, dataset-upload-based argv fix (ADR 0025), CUDA-enforcement + reproducibility + resume + checkpoint validation (ADR 0026) |
| Checkpoint resume / reproducibility / CI workflow timeout | ✅ Ready | ADR 0026, `.github/workflows/training-phase2-free-gpu-experiment.yml` |
| CostGuard / paid-GPU approval gate | ✅ Ready, untouched | ADR 0022 |

Manual trigger only (`workflow_dispatch`), never scheduled - a real
Kaggle GPU run is a deliberate, human-triggered action.

## 4. Security & auth

| Item | Status |
|---|---|
| Provider-independent auth, PBKDF2 + bearer tokens, ownership checks | ✅ Ready |
| Rate limiting (`/auth/*` by IP, generation by user) | ✅ Ready |
| Upload validation (content-type allowlist, bounded streaming) | ✅ Ready |
| Security headers (CSP, X-Frame-Options, HSTS, etc.) | ✅ Ready - `/demo` gets a page-appropriate CSP, every other route keeps `default-src 'none'` |
| Quota enforcement (per-workspace concurrent generation cap) | ✅ Ready, opt-in (`MAX_CONCURRENT_GENERATIONS_PER_WORKSPACE`) |

See `docs/adr/0020-security-hardening.md`.

## 5. Scale-out options (all opt-in via env var, `memory`/`local` remains default)

| Capability | Real backend | Verified against |
|---|---|---|
| `PROJECT_STORE=postgres` | `PostgresProjectStore` | Real local Postgres 16 |
| `EVENT_BUS=redis`, `TOKEN_STORE=redis`, `CACHE_BACKEND=redis`, `RATE_LIMITER=redis`, `QUOTA_ENFORCER=redis` | Real `RedisEventBus`/`RedisTokenStore`/`RedisCache`/etc. | Real local Redis 7 |
| `ORCHESTRATOR=temporal` | `TemporalProjectOrchestrator` | Real `temporal` CLI dev server, including worker-restart durability |
| `STORAGE_PROVIDER=s3` | `S3Provider` (`boto3`) | `moto`'s `ThreadedMotoServer` (real S3 REST API, not the exact MinIO/S3 binary - see ADR 0018's honesty note) |
| Observability (structured logs, OTel tracing, Prometheus metrics) | Real | `ConsoleSpanExporter`/`LoggingErrorReporter` real and complete; `OTLPSpanExporter`/`SentryErrorReporter` real SDK usage, unverified against a live collector/Sentry project |

None of these are required for v1.0.0 - they're independently-tested
upgrade paths for when scale actually demands them.

## 6. What a human must still do for the first real RunPod production run

Everything below requires access this development environment does not
have (a funded RunPod account, an unrestricted network) - the code and
CI/CD automation are real, complete, and already exercised end-to-end
in free/dry-run mode (§0); what's left is deployment actions (secrets,
approvals, account balance, one workflow run with `real_deploy=true`),
not missing engineering.

Steps 1-3 are now automated by `.github/workflows/deploy-runpod-endpoint.yml`
(runs on a real GitHub-hosted runner, which has neither restriction this
sandbox does). `real_deploy=false` (the default) already ran for real -
see §0 - and needs no further verification:

1. **Build and push the worker image** - automated by the workflow's
   `build-and-push` job (GHCR, using `GITHUB_TOKEN` - no extra registry
   secret needed). **Verified for real.**
2. **Deploy a real RunPod Serverless endpoint** from that image -
   automated by the workflow's `deploy-endpoint` job
   (`infra/runpod/deploy_endpoint.py`), gated by
   `real_deploy=true` + the `runpod-production-deploy` Environment's
   required reviewers. **Dry-run path verified for real; the real path
   reached RunPod's actual API and was correctly rejected for lacking
   account balance - not yet completed with a funded account.**
3. **Confirm it's healthy** - automated by the workflow's
   `verify-health` job (`infra/runpod/check_health.py`), result posted
   to the run's job summary. Only runs when `real_deploy=true`.

What's left, purely deployment/config actions, not something CI can do
for you:

4. **Add repository secrets**: `RUNPOD_API_KEY` (required), `HF_TOKEN`
   (optional - only if `models/registry.yaml`'s configured Wan2.2 repo
   becomes gated; public as of this writing).
5. **Fund the RunPod account** with at least $0.01 balance - RunPod's
   own API rejects endpoint creation otherwise (confirmed by the real
   rejection in run 30228235422).
6. **Configure the `runpod-production-deploy` Environment**'s required
   reviewers (Settings -> Environments) - the actual human approval gate.
7. **Run the workflow with `real_deploy=true`** (Actions -> "Deploy -
   RunPod Wan2.2 Production Endpoint" -> Run workflow -> check both
   `confirm_deploy` and `real_deploy` -> Run), approve when prompted,
   and copy the resulting `RUNPOD_ENDPOINT_ID` from the job summary.
8. **Point `apps/api` at it**: `COMPUTE_PROVIDER=runpod`,
   `RUNPOD_API_KEY`, `RUNPOD_ENDPOINT_ID`.
9. **Run one real end-to-end request** (a prompt through `/demo` or the
   full `/projects` REST flow) and confirm a real, full-quality Wan2.2
   clip comes back - the first genuinely unverified step in this whole
   pipeline, specifically because it needs infrastructure this
   development environment cannot provide.

Everything upstream of step 9 (the full creative pipeline, the exact
job payload shape, the real inference call's mechanism, the real HF
download/checksum logic, the RunPod HTTP client, the deployment
workflow itself, and now the entire free-mode CI path) has already been
verified for real, independently, up to the credentials/infrastructure
boundary - see `docs/adr/0026-pre-first-real-run-audit-fixes.md` and
the "Real video generation + RunPod production backend" entry in the
root `README.md`.

## 7. Test coverage

Full suite: 789 passed, 32 skipped (Redis/Temporal/real-GPU-only tests
that need a live optional service not running in this environment),
`ruff check .` clean, at the time of this release. Every skip is a real
`pytest.importorskip`/env-gated skip, not a disabled/xfail test hiding
a failure.

## Go / No-Go

**GO for the mock and local-inference paths (`COMPUTE_PROVIDER=local`/`local-inference`)
and the full creative pipeline** - genuinely production-ready today,
zero external dependencies beyond what's already tested.

**GO for Wan2.2 LoRA training on Kaggle's free GPU tier** - manually
triggered, cost-protected, all 8 blocking issues from the pre-first-run
audit resolved (ADR 0026).

**CONDITIONAL for `COMPUTE_PROVIDER=runpod` real production inference**
- code-complete, fails safely, and the entire pipeline up to RunPod's
own account-balance check has now run for real in CI (§0); requires the
remaining manual deployment steps in §6 (funded account, secrets,
Environment approval, one `real_deploy=true` run) before the first real
request. Not a code gap; an infrastructure/credentials/balance gap only
a human with a funded RunPod account can close.
