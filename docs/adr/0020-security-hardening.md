# ADR 0020: Security Hardening - rate limiting, token expiry, authorization, upload validation, secure headers, GPU quotas (Phase 8 WP5)

**Status:** Accepted

## Context

By the end of Phase 8 WP1 (ADR 0019), `apps/api` had real observability
but was otherwise unchanged from Phase 5: bearer tokens that never
expired, no rate limiting on any endpoint (including `/auth/login`,
a brute-force target, and `generate-video`, a real-money GPU-triggering
endpoint), one route (`GET /jobs/{job_id}`) with no authentication check
at all, unbounded file uploads (`file.file.read()` with no size or
content-type check), no defensive response headers, and no cap on how
many generations a single workspace could have in flight at once.
`docs/PHASE8_SCALEOUT_PLAN.md` items 6-8, 20-25 named these gaps
explicitly. Per the user's priority ordering, this is WP5, after WP1.

## Decisions

### 1. `packages/rate-limit-sdk`: `IRateLimiter`, fixed-window, in-memory + Redis

`allow(key, *, limit, window_seconds) -> RateLimitResult(allowed, remaining, retry_after_seconds)`.
A real fixed-window counter (resets `window_seconds` after the *first*
call in a window, not on a clock boundary) - simpler than a sliding
window and sufficient for the abuse-protection goal (bound the rate,
not guarantee perfectly smooth distribution). `InMemoryRateLimiter`
(dict-based, single process). `RedisRateLimiter` (`INCR` + `EXPIRE`,
real - counts are shared across every `apps/api` replica reading the
same Redis, fixing the multi-replica gap a process-local counter would
have). Two call-site keying strategies in `apps/api/src/api/rate_limit.py`:
`rate_limit_by_ip` (pre-auth endpoints - `/auth/register`, `/auth/login`
- no user id exists yet) and `rate_limit_by_user` (post-auth,
GPU-triggering endpoints - `generate-video`, `retry-generation` - keying
by IP would under-protect one user behind a rotating IP and
over-protect a NAT'd office behind one shared IP). A 429 response
always carries `Retry-After`.

### 2. Token TTL + rotation: `ITokenStore.set()` gains `ttl_seconds`, `IAuthProvider` gains `refresh_token()`

`ITokenStore.set(token, user_id, *, ttl_seconds=None)` mirrors
`ICache.set()`'s exact shape (`packages/cache-sdk`, ADR 0017) -
`None` (the default) means "never expires," so every pre-WP5 caller of
`InMemoryTokenStore`/`RedisTokenStore` is unaffected.
`InMemoryTokenStore` enforces TTL with an application-level expiry
check on `get()` (the same pattern `InMemoryCache` already uses);
`RedisTokenStore` maps it directly onto Redis's own key expiry
(`SET ... EX`). `LocalAuthProvider` takes a new `token_ttl_seconds: int
= 0` constructor param (`0` = never expires, unchanged default) and a
new `refresh_token(token) -> AuthToken` method: looks up the old
token's owner, deletes the old token, issues a new one (rotation, not
just extension - the old token can never be replayed after a refresh).
`POST /auth/refresh` reads the raw `Authorization` header directly
(not through `get_current_user`, which only ever returns the resolved
`User`, not the raw token string `refresh_token` needs to invalidate).

### 3. Authorization review: `GET/POST /jobs/{job_id}` had no auth check at all

The one real gap this review found: every project-scoped route already
enforced `record.created_by != current_user.user_id -> 403`, but
`GenerationJob` has no owner field of its own, only a `project_id` -
`routes/jobs.py`'s two routes took no `current_user` dependency
whatsoever, so any caller who could guess or enumerate a job id could
read (and, for retry, mutate) another workspace's generation job.
Fixed with `_get_owned_job(job_id, state, current_user)`: loads the
job, then loads its *owning project* via `state.project_store.get(job.project_id)`
and checks that project's `created_by` - both routes now require
`Depends(get_current_user)` and go through this helper. No other route
had this gap; every other project-scoped and asset-scoped route already
had an equivalent ownership check.

### 4. `packages/quota-sdk`: `IQuotaEnforcer`, a concurrency cap distinct from `IRateLimiter`

`acquire(scope, *, max_concurrent)` raises `QuotaExceededError` if
`scope` (a workspace id) already has `max_concurrent` operations in
flight, otherwise reserves a slot; `release(scope)` frees it. This is
deliberately a different primitive from `IRateLimiter`: a rate limiter
bounds how many operations may *start* per unit time, a quota enforcer
bounds how many may be *in flight* at once - the concrete cost being
protected here is GPU compute capacity/spend, not request volume.
`InMemoryQuotaEnforcer` uses a `threading.Lock`-protected dict.
`RedisQuotaEnforcer` does the check-and-increment inside a single
atomic Lua `EVAL` script (`_ACQUIRE_SCRIPT`) - a naive `INCR` + check +
`DECR`-on-reject sequence has a real race window where two processes
could both read "under capacity" before either increments; the Lua
script closes it. `ProjectLifecycle._run_generation` calls
`acquire()`/`release()` around the actual generation call, only when
both `quota_enforcer` is set *and* `max_concurrent_generations_per_workspace > 0`
(the default `0` means "no quota configured," identical to every
pre-WP5 environment) - `release()` runs in a `finally` so a slot is
always freed even when generation fails.

### 5. Upload hardening: content-type allowlist + bounded chunked reads

`POST /assets/upload` previously called `file.file.read()` once,
unbounded - a memory-exhaustion vector regardless of what
`Content-Length` a client claims (a client can lie about it or omit it
entirely), and accepted any `Content-Type`. Now validates
`file.content_type` against `state.upload_allowed_content_types` (415
if not allowed) before touching the body, then reads in
`_READ_CHUNK_BYTES = 1MiB` chunks via `while chunk := file.file.read(...)`,
rejecting (413) mid-stream the moment `state.upload_max_bytes` is
exceeded - the request is aborted as soon as the limit is crossed, not
after the whole body has already been buffered.

### 6. Secure response headers via a second `BaseHTTPMiddleware`, plus a real cross-middleware contextvar bug this surfaced

`SecurityHeadersMiddleware` adds `X-Content-Type-Options: nosniff`,
`X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`,
`Content-Security-Policy: default-src 'none'` (safe because `apps/api`
is a JSON-only API, never HTML/JS), `Strict-Transport-Security` (a
no-op over plain HTTP, meaningful once a deployment terminates TLS in
front of this process), and `Permissions-Policy` to every response.
Adding it as a *second* `BaseHTTPMiddleware` (alongside WP1's
`ObservabilityMiddleware`) broke `main.py`'s global exception handler's
ability to read the correlation id: confirmed via two minimal, isolated
Starlette `TestClient` repros (one with a single `BaseHTTPMiddleware`,
one with two stacked) that `BaseHTTPMiddleware.call_next()` spawns a
new child `anyio` task per layer, and a `ContextVar.set()` made inside
that child task is invisible once control returns to the parent task -
exactly the boundary `ServerErrorMiddleware` (which dispatches the
exception handler) sits across, outside every stacked middleware. Fixed
by also writing the correlation id onto `request.state.correlation_id`
(`ObservabilityMiddleware.dispatch`) - `request.state` is backed by the
ASGI `scope` dict, passed by reference through every nested task spawn,
so it survives a boundary the contextvar does not. `main.py`'s handler
and `SentryErrorReporter.capture_exception` both now prefer this
explicit value over the contextvar read. `_ContextFilter` (WP1's
logging filter) was also changed to only set `correlation_id`/`user_id`/
`project_id` on a `LogRecord` if not already present, so an explicit
`extra={"correlation_id": ...}` a caller passes is never clobbered by a
`None` contextvar read from inside a nested-task boundary. This was a
real regression caught by `tests/test_api_observability.py`'s existing
WP1 test failing after `SecurityHeadersMiddleware` was wired in, not a
hypothetical - see `tests/test_wp5_security_hardening.py::test_security_headers_present_on_unhandled_exception_response`
for the regression guard.

### 7. Every new limit is a `Settings` field with a safe, pre-WP5-identical default

`rate_limiter`/`quota_enforcer: str = "memory"` (same lazy-import-on-`"redis"`
swap-point pattern as `cache_backend`/`event_bus`/`token_store`, ADR
0017), `auth_rate_limit_per_minute: int = 20`,
`generation_rate_limit_per_minute: int = 10`, `token_store_ttl_seconds:
int = 0` (never expires), `upload_max_bytes: int = 25 * 1024 * 1024`,
`upload_allowed_content_types: str = "image/png,image/jpeg,image/webp,image/gif"`,
`max_concurrent_generations_per_workspace: int = 0` (no cap). None of
these change behavior for an environment that doesn't set them beyond
what a production deployment should already want (a bounded rate limit,
a bounded upload size) - `build_app_state()` is still the one place
that reads `Settings` and picks concrete implementations.

## Consequences

- `tests/test_wp5_security_hardening.py` (30 tests) covers every item
  above: `rate_limit_sdk`/`quota_sdk` unit tests (in-memory always run;
  Redis-backed variants run for real against a local Redis server and
  are skipped only if none is reachable, same convention as
  `test_redis_token_store.py`), token TTL expiry and `refresh_token`
  rotation/invalidation at the `packages/auth` level,
  `ProjectLifecycle` quota enforcement (rejection at capacity, slot
  release after completion, no-op when unconfigured), and end-to-end
  `TestClient` coverage of auth/generation rate limiting (429 +
  `Retry-After`), `/auth/refresh`, upload content-type/size rejection,
  and secure headers on success/error/unhandled-exception responses.
  `tests/test_api.py` gained the `jobs.py` ownership-check tests (401
  without auth, 403 for another user's job) as part of item 3.
- Full suite: 507 passed, 6 skipped (the pre-existing
  Temporal-dev-server-not-running skips, unrelated to this ADR) - every
  pre-WP5 test continues to pass unchanged; the four `AppState`
  direct-construction test sites were updated via a new
  `tests/conftest.py::default_wp5_app_state_kwargs()` helper that
  derives values from `Settings()`'s own defaults, so test defaults can
  never silently drift from what `build_app_state()` actually wires.
- This ADR does not change `IVideoEngine`, `IComputeProvider`,
  `GenerationPipeline`'s public contract, `IProjectStore`, `IEventBus`,
  or `CinematicIntelligenceCoordinator`. `ProjectLifecycle` gained two
  new optional constructor params (`quota_enforcer`,
  `max_concurrent_generations_per_workspace`, both defaulting to
  no-op/off) and `IAuthProvider`/`ITokenStore` each gained one new
  method/param, additive to their existing contracts - every existing
  caller of either interface is unaffected.
- `SentryErrorReporter` and `RedisRateLimiter`/`RedisQuotaEnforcer`/
  `RedisTokenStore` remain in the same honesty class established in
  prior ADRs: real, correct code, verified where a real backing service
  is reachable in this sandbox (Redis - fully verified) and
  unverified-by-necessity where it is not (a live Sentry project).
- `apps/api/pyproject.toml` was missing declared dependencies on
  `rate-limit-sdk`/`quota-sdk` despite `apps/api/src/api/state.py`
  importing both directly - the same class of gap ADR 0019 caught for
  `cache-sdk` (workspace-member packages install regardless via
  `uv sync --all-packages`, so the gap doesn't fail tests, only
  `apps/api`'s own declared contract). Fixed alongside this ADR.
- Remaining out of scope for WP5 (not gaps, deliberate boundaries): no
  WAF/DDoS-layer protection (expected to sit in front of `apps/api`,
  e.g. a cloud load balancer or CDN, not in application code); no
  per-endpoint fine-grained RBAC beyond the existing
  owner-vs-everyone-else model (`docs/adr/0011-frontend-and-auth.md`
  already scoped a full team/role model out); the fixed-window rate
  limiter's small race window under true concurrent Redis clients is
  accepted and documented in `packages/rate-limit-sdk`'s own docstring,
  not a hard security boundary.
