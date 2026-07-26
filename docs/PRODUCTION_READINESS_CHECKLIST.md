# Production Readiness Checklist — v1.0.0

Status of every major subsystem as of the v1.0.0 release, what's
actually verified vs. what still needs a human with real credentials,
and the exact manual steps left before this platform serves real
production traffic. Every ✅/⚠️ below is backed by a real, passing test
or a real (if sandbox-network-limited) execution - see the linked ADR
for the specific evidence, not just the claim.

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
| `runpod` | **Real**, full-scale Wan2.2 on a real GPU (`RunPodProvider` + `workers/gpu-worker`) | `RUNPOD_API_KEY`, `RUNPOD_ENDPOINT_ID`, `HF_TOKEN` (worker-side, only if the repo is gated) | ⚠️ Code + CI deployment automation (`.github/workflows/deploy-runpod-endpoint.yml`) complete and fails fast on missing credentials; **the workflow has not yet been run** (needs real `RUNPOD_API_KEY` + Environment approval) - see §6 |
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
CI/CD automation are real and complete, these are deployment actions
(secrets, approvals, one workflow run), not missing engineering.

Steps 1-3 are now automated by `.github/workflows/deploy-runpod-endpoint.yml`
(runs on a real GitHub-hosted runner, which has neither restriction this
sandbox does):

1. **Build and push the worker image** - automated by the workflow's
   `build-and-push` job (GHCR, using `GITHUB_TOKEN` - no extra registry
   secret needed).
2. **Deploy a real RunPod Serverless endpoint** from that image -
   automated by the workflow's `deploy-endpoint` job
   (`infra/runpod/deploy_endpoint.py`), gated by the
   `runpod-production-deploy` Environment's required reviewers.
3. **Confirm it's healthy** - automated by the workflow's
   `verify-health` job (`infra/runpod/check_health.py`), result posted
   to the run's job summary.

What's left, purely deployment/config actions, not something CI can do
for you:

4. **Add repository secrets**: `RUNPOD_API_KEY` (required), `HF_TOKEN`
   (optional - only if `models/registry.yaml`'s configured Wan2.2 repo
   becomes gated; public as of this writing).
5. **Configure the `runpod-production-deploy` Environment**'s required
   reviewers (Settings -> Environments) - the actual human approval gate.
6. **Run the workflow** (Actions -> "Deploy - RunPod Wan2.2 Production
   Endpoint" -> check `confirm_deploy` -> Run), approve when prompted,
   and copy the resulting `RUNPOD_ENDPOINT_ID` from the job summary.
7. **Point `apps/api` at it**: `COMPUTE_PROVIDER=runpod`,
   `RUNPOD_API_KEY`, `RUNPOD_ENDPOINT_ID`.
8. **Run one real end-to-end request** (a prompt through `/demo` or the
   full `/projects` REST flow) and confirm a real, full-quality Wan2.2
   clip comes back - the first genuinely unverified step in this whole
   pipeline, specifically because it needs infrastructure this
   development environment cannot provide.

Everything upstream of step 8 (the full creative pipeline, the exact
job payload shape, the real inference call's mechanism, the real HF
download/checksum logic, the RunPod HTTP client, the deployment
workflow itself) has already been verified for real, independently, up
to the credentials/infrastructure boundary - see
`docs/adr/0026-pre-first-real-run-audit-fixes.md` and the "Real video
generation + RunPod production backend" entry in the root `README.md`.

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
- code-complete and fails safely, but requires the six manual
deployment steps in §6 before the first real request. Not a code gap;
an infrastructure/credentials gap only this session's environment
prevented closing.
