# ADR 0011: Provider-independent auth, and building the frontend against a completed API contract

**Status:** Accepted

## Context

Phase 5 asks for a real user-facing product (`apps/web-dashboard`) on top
of the Phase 1-4 pipeline, plus "prepare: users, projects ownership,
permissions - keep it provider-independent," while explicitly not
rewriting the core pipeline. Three design questions fall out of that:

1. What does provider-independent auth look like, given the pattern
   already established for every other swappable dependency
   (`ILLMProvider`, `IVideoEngine`, `IComputeProvider`)?
2. Is a full team/workspace-membership model in scope?
3. Does `apps/api`'s existing contract actually support everything the
   frontend needs to build ("review storyboard", "review render spec"),
   or does building the frontend first reveal gaps in it?

## Decisions

### 1. `packages/auth`: `IUserStore` + `IAuthProvider`, same shape as every other provider

`LocalAuthProvider` (PBKDF2-HMAC-SHA256 password hashing via stdlib
`hashlib` - no bcrypt/argon2 build dependency; opaque `secrets.token_urlsafe`
bearer tokens held in memory) implements `IAuthProvider`; `apps/api`
depends only on that interface, never on hashing or token-storage
details. A production deployment swaps in an OAuth/OIDC-backed
`IAuthProvider` (Auth0, Clerk, ...) without `apps/api`'s route handlers
or dependency injection changing - identical to how `ClaudeProvider`/
`RunPodProvider` swap in for their local defaults (ADR 0001/0002).

`get_current_user` (a FastAPI dependency resolving `Authorization:
Bearer <token>` via `Depends(get_app_state)`, not by reading
`request.app.state` directly) is what makes this swap-through work in
tests too: `app.dependency_overrides[get_app_state]` redirects every
dependency that goes through it, including nested ones.

### 2. Personal workspace per user, not a team model

`LocalAuthProvider.register` assigns every new user a personal default
workspace (`workspace_id = f"ws_{user_id}"`). There is no invite/roles/
shared-workspace-membership model. "Prepare: ... permissions" is
satisfied by ownership checks (`record.created_by == current_user.user_id`,
403 otherwise) on every project-scoped route and `GET /projects` always
scoping to `current_user.workspace_id` (never a client-supplied query
param) - real, enforced, testable authorization, at the scope Phase 5
actually needs. A team/workspace-membership model is a clean additive
change on top of this (a `WorkspaceMembership` join, not a rewrite of
`IAuthProvider`), deferred rather than half-built now.

### 3. Building the frontend surfaced two real API gaps - fixed, not routed around

Building `apps/web-dashboard`'s storyboard/render-plan review screens
against the *existing* contract (a hard Phase 5 requirement - "do not
bypass the backend") surfaced that `apps/api` had no way to fetch
`DirectorPlan`/`Storyboard`/`RenderPlan` content at all: Phase 4 only
exposed the approve/reject *actions*, not the artifacts a human needs to
see before deciding. `IDirectorMemoryStore` already held this data since
Phase 1 - it just wasn't on `AppState` or exposed over HTTP. Added:
`GET /projects/{id}/plan`, `/storyboard`, `/render-plan` (ownership-checked
like every other project route, 404 until the relevant stage has run).

Second gap, found once the frontend actually ran in a browser rather than
via `httpx.TestClient`: `apps/api` had no CORS policy, so every
cross-origin `fetch()` from `localhost:3000` to `localhost:8000` was
blocked by the browser before it left the page.
`config_sdk.Settings.cors_allowed_origins` (default
`http://localhost:3000`) plus `CORSMiddleware` in `apps/api/main.py`
fixes this - `fastapi.testclient.TestClient` never exercises real
browser CORS preflight, so this class of bug is invisible to
`tests/test_api.py` no matter how thorough; it only surfaces by actually
running the frontend against the API in a real browser, which is exactly
what Phase 5's "run dev server, verify in browser" step is for.

### 4. `retry-generation` and `/assets/upload` complete the lifecycle/upload loop

`ProjectLifecycle.retry_generation` (requires `FAILED`, shares
`_run_generation` with `generate_video` rather than duplicating the
job-submission/status-mapping logic) backs `POST
/projects/{id}/retry-generation` - the "retry option" the Phase 5 spec
asks for on the real-time job status UI. `POST /assets/upload`
(multipart, `AssetManager.persist_local_copy` + `.register(kind="image")`)
is the reference-image upload flow: an asset can be filed under a
workspace before any project exists yet (`project_id` optional), then
its `asset_id` passed into `POST /projects`' `reference_asset_ids`.

## Consequences

- `apps/web-dashboard` (Next.js 16 App Router, TypeScript, Tailwind v4)
  talks to `apps/api` exclusively through `src/lib/apiClient.ts`, a
  typed wrapper covering every route above - no route was added to
  `apps/api` speculatively; each exists because a specific frontend
  screen needed it.
- `src/lib/types.ts` mirrors `packages/schemas/json/*.schema.json` by
  hand rather than a generation step - acceptable at this scale, revisit
  if the schema surface grows enough for drift risk to outweigh a
  codegen step's overhead.
- Bearer tokens live in `localStorage` (`src/lib/auth.tsx`) - acceptable
  for this phase's scope; a production hardening pass would consider
  httpOnly cookies to reduce XSS token-theft surface, deferred alongside
  the OAuth/OIDC `IAuthProvider` swap.
- The CORS and plan/storyboard/render-plan gaps were both found via
  actually running the stack (Playwright against a real Chromium browser
  hitting real `uvicorn`/`next dev` servers, not mocked) - the Phase 5
  verification step this ADR responds to earned its place in the process
  by catching bugs `tests/test_api.py`'s `TestClient`-based suite
  structurally cannot see.
