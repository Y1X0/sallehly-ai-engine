# ADR 0015: Temporal activation (Phase 8 WP6) - real execution, and the workflow redesign it required

**Status:** Accepted

## Context

`docs/PHASE8_SCALEOUT_PLAN.md`'s WP6 named `TemporalProjectOrchestrator`
plus a live worker as the highest-priority scale-out item - the piece
that decouples an HTTP request from the full render duration, and the
one part of ADR 0010's design that was written and "structurally
validated" (SDK decorators accepted, signal/query/activity names
registered) but never actually executed.

That "not executable" conclusion (ADR 0010 §3) turned out to be
narrower than stated. It was true of exactly one thing:
`temporalio.testing.WorkflowEnvironment`'s ephemeral test server, which
auto-downloads a native binary from `temporal.download` on first use -
a host this sandbox's egress policy blocks. A real `temporal` CLI
binary, downloaded directly from GitHub Releases (a host this sandbox's
egress policy does *not* block - confirmed empirically, not assumed),
runs `temporal server start-dev` here without issue, and a real
`temporalio.client.Client` connects to it. This is arguably a more
representative test than the ephemeral harness would have been anyway:
a real deployment never uses `WorkflowEnvironment` either, it connects
to a real cluster the same way this now does.

Attempting to actually drive `ProjectGenerationWorkflow` through that
real server immediately surfaced that the pre-WP6 design didn't match
`IProjectOrchestrator`'s contract: `run()` auto-chained
`create_project -> generate_creative_plan -> [wait for storyboard
signal] -> [wait for render signal] -> generate_video` as one
continuous execution, using `@workflow.signal` only for the two
approval gates. But `apps/api` calls `generate_creative_plan`,
`generate_video`, etc. as **independent, separately-triggered** HTTP
requests - there is no point in the real API flow where "project
created" implies "plan generation already happened," yet the old
workflow made exactly that assumption. This was invisible under
"structurally validated" testing because nothing had ever tried to
drive it action-by-action before.

## Decisions

### 1. Every `IProjectOrchestrator` method becomes one `@workflow.update`

`ProjectGenerationWorkflow` was redesigned: `run()` now does nothing
but `await workflow.wait_condition(lambda: self._closed)` - it's a
long-lived state-machine host, not a fixed sequential script. Every
lifecycle action (`generate_creative_plan`, `approve_storyboard`,
`reject_storyboard`, `approve_render_plan`, `reject_render_plan`,
`generate_video`, `retry_generation`, `finalize_project`) is a
`@workflow.update` - synchronous-from-the-caller's-perspective,
returns the resulting `ProjectRecord` dict directly, matching
`IProjectOrchestrator`'s exact one-call-per-action shape. `create_project`
is the one method with no update of its own name - it's folded into
workflow start via `Client.execute_update_with_start_workflow`
(`TemporalProjectOrchestrator.create_project`), so it's still exactly
one call from the caller's side. Temporal Updates (not Signals) were
chosen specifically because they return a value synchronously to the
caller - Signals are fire-and-forget, which would have needed a
separate polling round-trip to get the resulting `ProjectRecord` back,
adding complexity `IProjectOrchestrator`'s contract doesn't need.

The workflow intentionally never self-terminates except once a project
reaches `EXPORTED` - `retry_generation`/`finalize_project` can both be
called an arbitrary amount of time after `generate_video` finishes, so
the workflow must stay open and update-able until there's truly nothing
left a caller could do. A project simply abandoned at `FAILED`/
`COMPLETED` leaves its workflow open indefinitely - a known, documented
limitation (see Consequences), not addressed by this pass.

### 2. `create_project` generates its own id; that id becomes the Temporal workflow id

`ProjectLifecycle.create_project` gained an optional `project_id: str |
None = None` parameter (additive, defaults to the same `uuid.uuid4()`
generation every pre-Phase-8 caller already gets). `TemporalProjectOrchestrator.create_project`
is the one caller that supplies its own, using it as both the
`ProjectRecord.project_id` and the Temporal workflow id -
`WorkflowIDConflictPolicy.FAIL` then gives "can't create two projects
with the same id" for free, via Temporal's own duplicate-workflow-id
rejection, rather than needing separate application-level dedup logic.

### 3. `_run_update` unwraps `WorkflowUpdateFailedError` back to `ProjectLifecycleError`

Confirmed empirically (not assumed) via a real failed-activity round
trip against the live server: a failed update surfaces to
`Client.execute_update`/`execute_update_with_start_workflow` as
`WorkflowUpdateFailedError`, whose `.cause` is an `ActivityError`, whose
own `.cause` is an `ApplicationError` carrying the original exception's
class name (`.type`) and message (`.message`). `TemporalProjectOrchestrator._run_update`
walks that chain and re-raises the original `ProjectLifecycleError`
when `.type == "ProjectLifecycleError"` - so `apps/api`'s existing
`except ProjectLifecycleError: raise HTTPException(409, ...)` handling,
and every test written against `SyncProjectOrchestrator`'s exception
behavior, keep working unchanged regardless of which orchestrator is
selected. This is the compatibility guarantee the whole plan asked for,
verified against a real failure, not a mocked one.

### 4. Every activity call gets an explicit, bounded `RetryPolicy` with `non_retryable_error_types=["ProjectLifecycleError"]`

A second bug the live server caught immediately: Temporal's own default
`RetryPolicy` (used whenever a call doesn't specify one) retries
indefinitely with backoff. `ProjectLifecycleError` (e.g. "approving a
storyboard that isn't `waiting_storyboard_approval`") is a *permanent*
failure - retrying it fails identically forever, which means the
calling update RPC (and therefore the synchronous `IProjectOrchestrator`
caller on the other end - an `apps/api` request thread) would simply
hang rather than getting the same immediate error
`SyncProjectOrchestrator` raises. The "wrong state transition" test
genuinely hung until every activity call was given an explicit policy:
`maximum_attempts=1` for pure state-gate activities that either succeed
immediately or fail identically forever (`create_project`,
`approve_storyboard`, `approve_render_plan`), a small bounded retry
count for activities that call something genuinely transient-failure-prone
(LLM calls, GPU/ffmpeg calls), and `non_retryable_error_types` on
*every* policy so a `ProjectLifecycleError` never retries regardless of
which bucket an activity is in.

### 5. `ProjectActivities` needs an explicit `activity_executor`; the workflow module needs sandbox passthroughs

Two more real, previously-undetectable bugs, both artifacts of this
being the first time anything actually built a `Worker` from this code:

- `ProjectActivities`' methods are plain `def`, not `async def` (they
  call straight into the synchronous `ProjectLifecycle`) - `temporalio.worker.Worker`
  requires an explicit `activity_executor` (a `ThreadPoolExecutor`) for
  any non-async activity, or construction fails outright.
- `render_workflow.py`'s `from .activities import ...` (needed so
  `workflow.execute_activity` can reference `ProjectActivities.<method>`
  by real class/method object - the SDK's recommended, type-safe
  pattern) drags this whole workspace's business-logic dependency graph
  into the sandbox's determinism-checking re-import, since
  `render_orchestrator.workflows` is nested inside `render_orchestrator`
  and Python always runs a package's `__init__.py` first. Several
  first-party packages (`schemas`, `prompt_engine`, ...) do a one-time
  `Path(__file__).resolve()` at import time to locate a data directory -
  genuinely deterministic in practice, but the sandbox correctly refuses
  any filesystem call by default and has no way to know that. None of
  this business logic ever executes *inside* the sandbox at runtime -
  `ProjectActivities`/`ProjectLifecycle` only run inside the activity
  executor's thread pool, entirely outside it - so `build_worker()`
  passes every first-party workspace package through except
  `render_orchestrator` itself (the one package whose workflow code
  genuinely still needs sandboxed determinism-checking).

### 6. `ORCHESTRATOR=sync|temporal`, defaulting to `sync` - same swap-point discipline as every other provider

`config_sdk.Settings.orchestrator` (default `"sync"`, unchanged
behavior for every existing environment) selects between
`SyncProjectOrchestrator` and `TemporalProjectOrchestrator` in
`apps/api/state.py`'s `build_app_state()` - the same pattern
`VIDEO_ENGINE`/`LLM_PROVIDER`/`COMPUTE_PROVIDER` already use. Selecting
`temporal` requires a real Temporal server (`temporal_address`/
`temporal_namespace`) and a running worker
(`apps/api/src/api/temporal_worker.py`, a standalone process reusing
`build_app_state()`'s own wiring so the worker and the API agree on
which concrete providers are active without duplicating `state.py`).

## Consequences

- `tests/test_temporal_orchestrator.py` is genuinely executed against a
  live server (skipped, not failed, when none is reachable) - mirrors
  `tests/test_project_orchestrator.py`'s scenarios against
  `TemporalProjectOrchestrator` instead of `SyncProjectOrchestrator`,
  including a worker-restart durability test (stop one worker mid-project,
  start a fresh one on the same task queue, prove the remaining steps
  still complete correctly from Temporal's own event history alone).
- Today's in-memory stores (`InMemoryProjectStore` et al - WP2 hasn't
  landed yet) mean the worker and the API process must share the same
  `ProjectLifecycle`/store instances to see the same project state -
  true separate-process deployment (the actual point of a worker
  process) needs WP2's Postgres-backed stores first. This is a
  documented limitation of today's persistence layer, not of the
  Temporal wiring - `docs/PHASE8_SCALEOUT_PLAN.md`'s WP2 remains the
  next dependency.
- The workflow's "never self-terminates except at `EXPORTED`" design
  means an abandoned project (nobody ever calls `retry_generation`/
  `finalize_project` after a `FAILED`/`COMPLETED` state) leaves its
  workflow open indefinitely. A TTL-based auto-close or `continue_as_new`
  policy is the production-hardening follow-up, not attempted here.
- `apps/api`'s default behavior is completely unchanged -
  `ORCHESTRATOR` defaults to `sync`, and every pre-WP6 test/environment
  is unaffected. Selecting `temporal` is opt-in, config-driven, and now
  genuinely tested rather than aspirational.
- This ADR does not change `IVideoEngine`, `IComputeProvider`,
  `GenerationPipeline`, or `CinematicIntelligenceCoordinator` in any
  way - `TemporalProjectOrchestrator` is a new implementation of
  `IProjectOrchestrator`, the interface `apps/api` already depended on
  exclusively.
