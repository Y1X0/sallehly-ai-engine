# ADR 0010: Persistence reuse, ProjectLifecycle, and the Temporal/sync duality

**Status:** Accepted

## Context

Phase 4 asks for durable workflows, real approval-gate signals, a
production API, database abstractions for six entities, an event system,
and a fully offline local developer experience - without changing the
CreativeDirector/CreativeCompiler/VideoEngine/ComputeProvider boundaries
established in ADR 0001/0002. Four separate design questions fall out of
that:

1. Do the six entities (Project, DirectorPlan, Storyboard, RenderSpec,
   GenerationJob, Asset) each need a new repository?
2. Where does the actual "create project → ... → generate video" logic
   live, given both a Temporal workflow and a plain API need to drive it?
3. Can Temporal actually be exercised in this environment?
4. How does `apps/api` answer arbitrary requests without a live Claude
   account, so its endpoints are genuinely testable here?

## Decisions

### 1. Only `Project` gets a new store

`IDirectorMemoryStore` (Phase 1) already persists DirectorPlan/Storyboard/
RenderPlan (keyed by project_id + stage); `IGenerationJobStore` (Phase 3)
already persists GenerationJob; `AssetManager` (Phase 3) already persists
Asset, with versioning. Building three more repositories would duplicate
working, already-tested code. `packages/persistence`'s `IProjectStore` +
`ProjectRecord` is the one genuinely new entity - the top-level record
tying a request to everything else, with `generation_job_ids`/`asset_ids`
as references rather than embedding those stores' data. See
`packages/persistence/README.md`.

### 2. `ProjectLifecycle` is the only place the flow's logic lives

`services/render-orchestrator/project_lifecycle.py` implements every
transition (`create_project`, `generate_creative_plan`,
`approve_storyboard`/`reject_storyboard`, `approve_render_plan`/
`reject_render_plan`, `generate_video`) by composing `CreativeDirector` +
`CreativeCompiler` + `GenerationPipeline` + `IProjectStore`, publishing an
`Event` at each step. Two things call it, and neither reimplements it:

- `SyncProjectOrchestrator` calls its methods directly, synchronously.
- `ProjectGenerationWorkflow`'s activities (`workflows/activities.py`)
  each call exactly one `ProjectLifecycle` method.

`apps/api` depends on `IProjectOrchestrator` (implemented today by
`SyncProjectOrchestrator`), not on `ProjectLifecycle` directly and not on
Temporal - a future `TemporalProjectOrchestrator` (starting/signaling a
real workflow via `temporalio.client.Client`) implements the same
interface, so route handlers never change when that swap happens.

### 3. Temporal: real code, not executable in this environment

**Update (Phase 8 WP6, [ADR 0015](0015-temporal-activation.md)):** this
section's conclusion turned out to be narrower than stated - genuinely
true of `temporalio.testing.WorkflowEnvironment`'s ephemeral test
server specifically (see below), not of running Temporal in this
environment at all. A real `temporal` CLI dev server, downloaded
directly from GitHub Releases rather than through the SDK's own
`temporal.download` auto-downloader, runs here without issue, and
`ProjectGenerationWorkflow`/`ProjectActivities`/`TemporalProjectOrchestrator`
are now genuinely executed against it (`tests/test_temporal_orchestrator.py`).
The rest of this section is preserved as an accurate record of what was
true and knowable at Phase 4.

`temporalio` installs and imports cleanly, and
`workflow._Definition.from_class(ProjectGenerationWorkflow)` /
`ProjectActivities.*.__temporal_activity_definition` confirm every
signal (`approve_storyboard`, `reject_storyboard`, `approve_render_plan`,
`reject_render_plan`), query (`status`, `project_id`), and activity
(`create_project`, `generate_creative_plan`, ...) registers correctly
with the SDK. Actually *running* it - even via
`temporalio.testing.WorkflowEnvironment.start_time_skipping()`, which
needs no real cluster - fails in this sandbox:

```
RuntimeError: Failed starting test server: error sending request for url
(https://temporal.download/temporal-test-server/...)
```

The ephemeral test server is a native binary downloaded on first use;
this sandbox's network policy blocks that host. This is the same class
of limitation as Phase 3's live GPU inference (`workers/gpu-worker`
needs a real deployment) - real, correct, deployable code that this
specific environment cannot execute. `docker compose --profile temporal
up` plus a worker process (`Worker(client, workflows=[ProjectGenerationWorkflow],
activities=ProjectActivities(lifecycle).all_activities())`) is how it
would actually run and be tested, per `docs/DEV_SETUP.md`.

### 4. `LocalHeuristicLLMProvider` for a fully offline API

`FakeLLMProvider` (Phase 1) only answers a fixed, pre-scripted sequence
of calls - fine for unit tests, not for a running server handling
arbitrary requests. `LocalHeuristicLLMProvider`
(`packages/llm-providers`) uses keyword/regex rules to produce
schema-valid `CreativeBrief`/`StoryOutline` output for *any* prompt, with
zero network access. `apps/api/src/api/state.py` uses it by default
(falling back to `ClaudeProvider` only if `ANTHROPIC_API_KEY` is set) -
this is what makes `tests/test_api.py` able to drive a project through
its entire lifecycle over real HTTP with no external dependency at all.
Never appropriate for production - it does not understand the brief, it
pattern-matches it.

## Consequences

- `ProjectStatus` (`packages/persistence`) intentionally includes the
  exact `WAITING_STORYBOARD_APPROVAL`/`WAITING_RENDER_APPROVAL`/
  `APPROVED`/`REJECTED` vocabulary requested, plus `CREATED`/`PLANNING`/
  `GENERATING`/`COMPLETED`/`FAILED` for the states around them. `REJECTED`
  is generic with a `rejected_stage` field (`"storyboard"` or
  `"render_plan"`) rather than two separate rejected states, since
  "regenerate affected stage only" needs to know which stage without
  needing two near-duplicate states.
- Rejecting a stage immediately regenerates it (`reject_storyboard`
  re-invokes `CreativeDirector.regenerate_with_feedback` +
  `CreativeCompiler.compile_storyboard`; `reject_render_plan`
  re-invokes `CreativeCompiler.compile_render_plan`, optionally with a
  new `quality_tier`) rather than leaving the project in `REJECTED`
  awaiting a separate "regenerate" call - simpler for API consumers, and
  "reject with feedback" and "regenerate" were never going to be used
  independently in practice.
- Adding a Postgres-backed `IProjectStore` (or `IDirectorMemoryStore`/
  `IGenerationJobStore`/`AssetManager` implementation) is additive to
  every layer above it - `ProjectLifecycle` never changes.
- When a real Temporal server becomes available, verifying
  `ProjectGenerationWorkflow` end-to-end (including crash-and-resume) is
  the next concrete step - the workflow code is written and structurally
  validated now specifically so that verification is the only thing
  left, not a rewrite.
