# Phase 8 Scale-out: Production-Readiness Engineering Plan

**Status:** In progress - WP6 (Temporal activation, ADR 0015), WP2
(Postgres-backed `IProjectStore`, ADR 0016), WP3 (Redis-backed
cache/event bus/token store, ADR 0017), WP4 (S3-compatible
`IStorageProvider`, ADR 0018), and WP1 (observability: structured
logging, tracing, metrics, error reporting, ADR 0019) are done. WP5,
WP7-13 remain not started.

## 0. Scope

Phase 8 pipeline integration (Cinematic Intelligence + post-production
wired into `ProjectLifecycle`/`apps/api`/`apps/web-dashboard`) is done -
see [ADR 0014](adr/0014-pipeline-integration.md). This document covers
the *other* half of Phase 8 already named in `docs/ARCHITECTURE.md`'s
roadmap - "`VastAIProvider` completion, `KubernetesProvider`,
autoscaling, caching, billing" - expanded into a full engineering plan
per your five categories (infrastructure scaling, production readiness,
AI generation infrastructure, security, business layer).

**Explicitly out of scope:** Phase 9 (`services/training`, a trained
Sallehly model). This plan's job is to make the platform ready for real
users and real GPU workloads *before* that starts - nothing here trains
a model or changes `SallehlyModelAdapter`'s current honest
"`SallehlyModelNotTrainedError`" behavior.

No code has been written for anything below. This is architecture
review + roadmap only, as requested.

---

## 1. Architecture review (current state)

Grounded in the actual code, not assumptions - every claim below was
verified against this repository.

### 1.1 Infrastructure scaling

- **`IComputeProvider` has three implementations**: `LocalProvider`
  (real, dev/test, no GPU), `RunPodProvider` (real production HTTP
  client with retry-with-backoff, but tested only against
  `httpx.MockTransport` - never against a live RunPod account), and
  `VastAIProvider`, which is a genuine four-method `NotImplementedError`
  stub.
- **No queue exists.** `GenerationPipeline.generate_shot` is fully
  synchronous: `submit()` → a blocking `while` loop calling
  `get_status()` with `time.sleep(poll_interval_sec)` → `fetch_output()`
  → `parse_result()`. `generate_plan` calls this once per shot in a
  plain sequential loop - no concurrency across shots, no
  broker/worker-pool separation. `apps/api` drives this through
  `SyncProjectOrchestrator`, so **the HTTP request thread that calls
  `POST /projects/{id}/generate-video` blocks for the entire multi-shot
  render** (up to `poll_timeout_sec=300` per shot, sequentially). FastAPI
  runs sync route handlers in Starlette's threadpool (default 40
  threads), so this doesn't hard-serialize all traffic to one request at
  a time, but it does mean the threadpool - and therefore the whole
  API's responsiveness - degrades directly with concurrent generation
  load. This is the single biggest scalability gap found.
- **A real durable-workflow path already exists but is dormant.**
  `ProjectGenerationWorkflow` + `ProjectActivities` (Temporal) are
  written and structurally validated (ADR 0010) - each activity thinly
  wraps one `ProjectLifecycle` method, exactly the decoupling a queue
  would provide. But **no `TemporalProjectOrchestrator` class exists** -
  `IProjectOrchestrator` has exactly one implementation
  (`SyncProjectOrchestrator`), and `apps/api/state.py` only ever
  constructs that one. The workflow can't run anywhere in production
  until a client-side driver is written and a live Temporal server
  exists. (This sandbox's inability to execute it is a sandbox-specific
  binary-download restriction, not a production blocker - a normal cloud
  environment has no such restriction.)
- **No GPU scheduling.** `EngineJobPayload.resources`
  (`min_vram_gb`/`gpu_count`) is populated declaratively by every
  `IVideoEngine.build_job_payload()`, but nothing downstream reads it -
  RunPod endpoints are pre-configured with a fixed GPU type
  (`infra/runpod/README.md` describes this as manual config, not code),
  and Vast.ai instance selection is entirely manual today.
- **No autoscaling policy is configured anywhere** - `infra/runpod/`,
  `infra/kubernetes/`, and `infra/terraform/` are all placeholder
  READMEs with no actual Terraform/Helm/endpoint config.
- **No per-workspace or global concurrency cap** - a client can submit
  unlimited concurrent `generate-video` calls today.

### 1.2 Production readiness

- **Redis, Postgres, and MinIO already run in `docker-compose.yml`**,
  and their connection strings are already declared in
  `config_sdk.Settings`/`.env.example`
  (`database_url`/`redis_url`/`storage_endpoint_url`/...) - but **no
  application code reads any of them**. Every store
  (`IProjectStore`, `IGenerationJobStore`, `IUserStore`,
  `IDirectorMemoryStore`, `IEventBus`) has exactly one implementation,
  and it's in-memory. `AssetManager`'s default `IStorageProvider` is
  `LocalFilesystemStorageProvider`; no S3-compatible implementation
  exists. This means: no data survives a process restart, and nothing
  can run as more than one API replica (each replica would have its own
  disconnected in-memory world).
- **No database migration tooling** - no Alembic, no SQLAlchemy models,
  no schema-migration story anywhere in the repo.
- **`packages/observability` is genuinely empty** - one blank
  `__init__.py`. Confirmed via search: there is not one
  `logging.getLogger` call anywhere in `services/` or `apps/`. No
  structured logging, no request-id correlation, no tracing, no metrics.
- **No error tracking integration** (no Sentry or equivalent) anywhere.

### 1.3 AI generation infrastructure

- **`workers/gpu-worker/handler.py` is a genuine stub**
  (`NotImplementedError`) - no real Wan2.1 inference code exists. This
  is expected and correct for this environment (no GPU hardware here),
  not a regression.
- **`RunPodProvider` is production-grade code that has never touched a
  live RunPod account** - contract-correct, untested against reality.
- **`infra/runpod/` has no actual deployment artifact** - just a README
  describing what an endpoint config should contain.
- **The video-engine swap point itself is solid** -
  `VIDEO_ENGINE_REGISTRY`/`Settings.video_engine` genuinely select
  between `Wan21Adapter` and `SallehlyModelAdapter` (fixed and proven in
  Phase 8 pipeline integration, ADR 0014). This part needs no further
  work for scale-out.

### 1.4 Security

- **`LocalAuthProvider`**: PBKDF2-HMAC-SHA256, 200k iterations (a
  reasonable hash) - but bearer tokens **never expire**, have no refresh
  mechanism, and live in a plain in-memory `dict[token, user_id]`. That
  dict is per-process: a token issued by one API replica is invisible to
  another the moment there's more than one.
- **No rate limiting anywhere** - confirmed via search, zero hits for
  rate-limit/throttle logic in `apps/api` or `packages/auth`. Both
  brute-force login attempts and generation-triggering endpoints are
  currently unthrottled.
- **Ownership checks are solid** - every project-scoped route correctly
  403s a non-owner, and this is well-tested. No gap here.
- **`POST /assets/upload` has no server-side file-size limit or
  content-type allowlist** in the route handler.
- **No secrets-management story beyond `.env` files** - fine for local
  dev, not for production.
- **No CI configuration exists in this repository at all** (no
  `.github/workflows/`, no equivalent) - worth flagging even though it's
  adjacent to, not strictly part of, this plan's five categories.

### 1.5 Business layer

- **Zero code, zero schema, zero mention anywhere.** Confirmed via
  search across the whole repo for billing/credits/quota/usage-tracking
  terms. This is greenfield, not a gap in something half-built.

---

## 2. Missing components (by category)

### Infrastructure scaling
1. `VastAIProvider` real implementation (4 methods) + a companion
   self-hosted job-runner HTTP service (`infra/vastai/` - referenced by
   `VastAIProvider`'s own docstring, doesn't exist as a directory yet).
2. `TemporalProjectOrchestrator` (new `IProjectOrchestrator`
   implementation) - the piece that actually activates the
   already-written Temporal workflow.
3. A live Temporal server (managed or self-hosted) + a worker process
   running `ProjectActivities`.
4. GPU scheduling: translate `EngineJobPayload.resources` into real
   RunPod GPU-type selection / Vast.ai instance search filters.
5. Autoscaling policy: RunPod Serverless min/max worker config
   (`infra/runpod/`, currently just a README); for a future Kubernetes
   path, HPA/KEDA scaling on queue depth.
6. `KubernetesProvider` (new `IComputeProvider`) + Helm charts for a GPU
   node pool (`infra/kubernetes/` is empty).
7. A per-workspace/global concurrency cap on in-flight generation jobs.

### Production readiness
8. `PostgresProjectStore` / `PostgresGenerationJobStore` /
   `PostgresUserStore` / `PostgresDirectorMemoryStore` implementing the
   existing `I*Store` interfaces, + SQLAlchemy models + Alembic
   migrations.
9. `S3Provider(IStorageProvider)` - tested against the already-running
   MinIO container before pointing at real S3/R2.
10. A Redis-backed cache layer (candidates: capability-manifest lookups,
    prompt-template renders, project-list pagination).
11. `RedisEventBus` (or a Redis-Streams-backed `IEventBus`) - needed the
    moment there's more than one API process, since
    `InMemoryEventBus` subscribers only see events published within the
    same process.
12. Structured logging (`packages/observability`, currently empty) +
    request-id correlation middleware.
13. OpenTelemetry tracing (spans tagged with `project_id`/`shot_id`/
    `engine_id`, per that package's own README) exported to an APM
    backend (vendor TBD).
14. Metrics (request latency, generation-job duration, queue depth).
15. Error tracking (Sentry SDK or equivalent) in `apps/api` and worker
    processes.
16. Alembic migration tooling + a documented cutover plan from
    `InMemory*` to `Postgres*`.

### AI generation infrastructure
17. Real `handler.py` implementation - load Wan2.1 once at process
    start, run inference, upload result, return
    `{output_uri, engine_metadata}`. Genuine ML/infra work requiring GPU
    hardware this sandbox doesn't have.
18. RunPod endpoint deployment (build+push the worker image, create the
    Serverless endpoint, wire `RUNPOD_ENDPOINT_ID`) - an infra step, not
    code.
19. A documented cold-start/warm-pool tradeoff (RunPod bills for idle
    warm workers) once real usage patterns are known.
20. `infra/vastai/` job-runner service (see item 1) - reuses
    `workers/gpu-worker`'s `handler.run`.
21. Cost-aware routing: `quality_tier`-aware provider/GPU selection
    (preview → cheaper GPU, final → full), RunPod idle-timeout tuning.

### Security
22. Token expiry + refresh (or a TTL-backed token in Redis instead of an
    in-memory dict - also fixes the multi-replica token-recognition gap).
23. Rate limiting middleware (per-user and per-IP) on auth endpoints and
    on generation-triggering endpoints.
24. Upload validation: max file size, content-type allowlist.
25. Workspace-scoped resource limits (max concurrent projects/jobs) -
    security *and* business concern (item 30).
26. Signed URLs / access control on S3-backed assets, once item 9 lands
    - a generated video shouldn't be publicly readable by guessing a
    URL.
27. Secrets management for production (out of `.env` files) - a
    `Settings` source swap, no shape change.
28. Audit logging for auth events and ownership-check failures.
29. Dependency/container vulnerability scanning in CI (no CI exists
    today).

### Business layer
30. Usage tracking - most naturally a new `IEventBus` subscriber
    consuming the already-firing `GENERATION_STARTED`/`COMPLETED`/
    `EXPORT_COMPLETED` events, with zero changes to `ProjectLifecycle`.
31. A credits/ledger schema (new JSON Schema, following this repo's
    existing per-artifact convention) + `ICreditLedger` interface +
    concrete implementation.
32. **A pricing-model decision from you** (pay-per-generation vs.
    subscription vs. hybrid) - blocks the ledger schema's design.
33. `IBillingProvider` + a Stripe (or similar) implementation, plus a
    webhook route in `apps/api`.
34. Quota enforcement as an additive pre-check inside
    `ProjectLifecycle.generate_video` (reject with `ProjectLifecycleError`
    if balance insufficient - same error class already in use, no new
    interface).
35. Usage dashboards in `apps/web-dashboard`.

---

## 3. Implementation roadmap (dependency-ordered)

Complexity: **S** (1-3 days) · **M** (1-2 weeks) · **L** (2-4 weeks) ·
**XL** (4+ weeks or needs dedicated infra/ML effort, not just app code).

| # | Work package | Category | Complexity | Depends on | Notes |
|---|---|---|---|---|---|
| WP1 | Structured logging + request-id correlation (`packages/observability`) | Production readiness | S | — | Do first - makes every later work package debuggable. Low risk. |
| WP2 | Postgres-backed stores (`PostgresProjectStore` et al.) + Alembic | Production readiness | L | WP1 | Highest-priority durability item. See Risk 2. |
| WP3 | Redis: cache + `RedisEventBus` + token store | Production readiness | M | — | Independent of WP2, but naturally pairs with it. |
| WP4 | `S3Provider(IStorageProvider)` | Production readiness | S/M | — | Test against the already-running MinIO container first. |
| WP5 | Rate limiting + token expiry/refresh | Security | S/M | WP3 | Hard gate before real user signups (Risk 6). |
| WP6 | `TemporalProjectOrchestrator` + live Temporal deployment + worker | Infra scaling | M/L | WP2 | Highest-leverage item for "real GPU workloads" - decouples HTTP requests from render duration. |
| WP7 | `VastAIProvider` + `infra/vastai/` job-runner | Infra scaling | M | — | Parallelizable with WP1-6; same well-understood pattern as `RunPodProvider`. |
| WP8 | Tracing + metrics + error tracking maturity | Production readiness | M | WP1 | Incremental; deepens naturally once WP6 adds more moving parts to trace. |
| WP9 | Real GPU worker deployment (`handler.py` + RunPod endpoint) | AI generation infra | XL | — | **Requires a human with GPU hardware/cloud access** - not executable or verifiable by a coding agent in this sandbox. Parallelizable with everything else. |
| WP10 | GPU scheduling + autoscaling + cost-aware routing | Infra scaling | M | WP9 | No point scheduling against a stub. |
| WP11 | Asset protection (signed URLs) | Security | S/M | WP4 | |
| WP12 | Usage tracking (`IEventBus` consumer) | Business | S/M | WP2 | |
| WP13 | Credits/billing (ledger schema, `IBillingProvider`, quota enforcement) | Business | L | WP12 + **pricing decision from you** | Explicit decision gate - see Open Decisions. |
| WP14 | `KubernetesProvider` + Helm charts | Infra scaling | XL | — | **Deferred/optional** - trigger-based (RunPod/Vast.ai cost or capacity actually becomes a bottleneck), not calendar-based. Avoid speculative infra investment. |

**Recommended sequence:** WP1 → WP2 → WP3 → WP4 → WP5 → WP6 → (WP7, WP8,
WP9 in parallel) → WP10 → WP11 → WP12 → WP13 → WP14 (only if/when
triggered).

---

## 4. Compatibility with existing interfaces

Every work package above is a **new implementation behind an interface
that already exists**, or an **additive check** using an error class
that already exists - the same swap-point discipline this codebase has
held since Phase 0/ADR 0001. Specifically:

- **`IVideoEngine`**: unchanged. WP9/WP10 are about *where and how*
  `IComputeProvider` executes a payload `Wan21Adapter`/
  `SallehlyModelAdapter` already build - no method signature changes.
- **`IComputeProvider`**: unchanged (4 methods). `VastAIProvider` (WP7)
  and `KubernetesProvider` (WP14) are new implementations registered
  into the existing `COMPUTE_PROVIDER_REGISTRY`, exactly like
  `RunPodProvider`/`LocalProvider` already are.
- **`GenerationPipeline`**: unchanged public contract
  (`generate_shot`/`generate_plan`). WP6 changes *who calls* it (a
  Temporal activity instead of a synchronous orchestrator call), not its
  signature or behavior.
- **`ProjectLifecycle`**: unchanged public method signatures. WP13's
  quota check and WP5's rate limiting are additive pre-checks that raise
  `ProjectLifecycleError` - the same class `_require`'s status checks
  already raise - not a new interface.
- **`CinematicIntelligenceCoordinator`**: **entirely untouched by this
  plan.** None of the five categories change cinematic-intelligence
  logic; explicitly confirmed zero planned changes to its public
  methods (`enrich_render_plan`/`get_project_report`/`improve_prompt`/
  `repair_shot`/`review_repair`/`list_repairs`).
- **`I*Store`/`IEventBus`/`IStorageProvider`/`IAuthProvider`**: WP2/WP3/
  WP4/WP5 are all new implementations of interfaces that already exist
  and are already exercised by `tests/conftest.py`'s `build_stack()` -
  the existing 422-test suite is the regression safety net for every
  store swap (see Risk 1).

---

## 5. Risks

1. **Regression safety net already exists.** Swapping `InMemoryProjectStore`
   → `PostgresProjectStore` (etc.) should be validated by re-running the
   *same* `tests/conftest.py`-based suite with the new store injected -
   if the interface contract is honored, the existing 422 tests should
   pass unmodified. Treat any test that needs *changing* (not just
   re-pointing) as a signal the new store broke a contract.
2. **Concurrency correctness.** `ProjectLifecycle._transition` currently
   assumes single-writer semantics. Multiple API replicas writing to a
   shared Postgres store need either row-level locking
   (`SELECT ... FOR UPDATE`) or optimistic concurrency (a version column
   on `ProjectRecord`) to prevent lost updates from concurrent
   approve/reject calls on the same project. Not addressed by simply
   swapping the store implementation - needs explicit design in WP2.
3. **Temporal is new operational surface.** Its own persistence store,
   monitoring, and upgrade cadence are a real ongoing cost. Recommend
   Temporal Cloud (managed) over self-hosting initially, given no
   existing operational experience running a Temporal cluster.
4. **GPU cost risk.** RunPod Serverless bills per-second while a worker
   is warm. Without WP10's scheduling and idle-timeout tuning, cost can
   balloon before it's noticed. Model this before opening real signups.
5. **GPU capacity risk.** RunPod/Vast.ai GPU availability isn't
   guaranteed for every GPU type at every moment. Production readiness
   should include a queueing UX for "no capacity right now" (partially
   supported already by `GenerationJob`'s `queued`/`running` states),
   not an assumption of instant availability.
6. **Security review gate.** Recommend treating WP5 (rate limiting +
   token expiry) as a hard gate before any real user signup is opened,
   and running an explicit security review pass before declaring this
   plan's security category "done."
7. **Billing correctness risk.** Double-charging or under-charging a
   user is trust-destroying. WP13's ledger should be append-only/
   event-sourced rather than a mutable balance column, with a
   reconciliation job cross-checking ledger totals against the payment
   provider's own records - a design requirement to carry into WP13,
   not yet decided here.
8. **Scope risk on WP9/WP14.** Real GPU inference deployment and
   Kubernetes cluster operation both require capabilities (GPU hardware
   access, cluster ops) outside what a coding agent in this sandbox can
   execute or verify. These are human-owned infrastructure work items;
   this agent's role there is code review of the handler/adapter
   contract, not autonomous end-to-end implementation.

---

## 6. Open decisions needed from you

Mirroring this repo's existing "Open decision: repository license"
entry in `docs/DECISIONS.md` - these genuinely can't be assumed:

1. **Pricing model** (WP13): pay-per-generation, subscription tiers, or
   hybrid? Blocks the credits/ledger schema design.
2. **Temporal deployment**: managed (Temporal Cloud) or self-hosted
   (WP6)? Affects operational risk and cost.
3. **Cloud provider** for Postgres/S3/Kubernetes (AWS/GCP/Azure, or
   staying Vast.ai/RunPod-only for compute with a separate cloud for
   storage/DB)?
4. **GPU deployment timing** (WP9): do you have GPU hardware/cloud
   budget available now, or should this stay explicitly deferred until
   it is?

---

## 7. Summary

WP6 (durable workflow execution, `TemporalProjectOrchestrator` genuinely
executed against a real `temporal` CLI dev server - ADR 0015), WP2
(durable stores, `PostgresProjectStore` genuinely executed against a
real local Postgres server with an applied Alembic migration - ADR 0016),
WP3 (`ICache`/`RedisEventBus`/`ITokenStore`'s Redis implementations
genuinely executed against a real local Redis server - ADR 0017), WP4
(`S3Provider`, tested against `moto`'s real S3-REST-API test server
since a live MinIO/S3 endpoint is unreachable here - ADR 0018), and WP1
(structured logging, real OpenTelemetry tracing, Prometheus metrics,
error reporting, all genuinely wired into `apps/api` and
`ProjectLifecycle`/`GenerationPipeline`/`TemporalProjectOrchestrator` -
ADR 0019) are done, per your explicit instruction to do WP6 first, then
databases and storage, then observability and security hardening.
WP5 (the security gate) remains the last piece of that instruction
still to land, then `VastAIProvider`/observability maturity/GPU worker
deployment in parallel, GPU scheduling once real GPU workers exist, and
the business layer last - gated on a pricing decision from you.
`KubernetesProvider` stays deferred until RunPod/Vast.ai actually
becomes a bottleneck. Every item is a new implementation behind an
interface this codebase already has, or additive instrumentation inside
existing methods - zero planned changes to `IVideoEngine`,
`IComputeProvider`, `GenerationPipeline`'s public contract,
`ProjectLifecycle`'s public contract, or `CinematicIntelligenceCoordinator`;
WP6, WP2, WP3, WP4, and WP1 all held to that, confirmed above.
