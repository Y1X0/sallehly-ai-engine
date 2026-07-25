# ADR 0016: Postgres-backed `IProjectStore` (Phase 8 WP2)

**Status:** Accepted

## Context

`docs/PHASE8_SCALEOUT_PLAN.md`'s WP2 named a real Postgres-backed
`IProjectStore` as the item that unblocks two things WP6 (ADR 0015)
explicitly flagged as its own remaining limitation: running the API
process and a Temporal worker as genuinely separate OS processes (they
must currently share one in-process `InMemoryProjectStore` to see the
same project state), and surviving an API process restart without
losing every in-flight project. `InMemoryProjectStore` also has the
concurrent-writer risk `docs/PHASE8_SCALEOUT_PLAN.md`'s Risk 2 named: two
callers racing to update the same project (a retried Temporal activity
and a direct API call, for instance) can silently clobber each other's
write with a plain Python dict.

This sandbox has a real, natively-installed Postgres 16 server (not
Docker - `docker pull postgres:...` hits the same blocked-registry issue
ADR 0015 hit for `temporalio/admin-tools`) reachable at
`postgresql+psycopg://sallehly:sallehly@localhost:5432/video_engine`,
matching `config_sdk.Settings.database_url`'s default exactly. Every
claim below was verified by actually running it, the same bar ADR 0015
set for Temporal.

## Decisions

### 1. SQLAlchemy Core (not the ORM), one `projects` table, JSON-as-text columns

`PostgresProjectStore` (`packages/persistence/src/persistence/postgres_store.py`)
uses a plain `sqlalchemy.Table` and `engine.connect()`/`engine.begin()`
- no declarative ORM models, no `Session`. `ProjectRecord` already has a
clean `to_dict()`/`from_dict()` pair (the latter added for
`TemporalProjectOrchestrator`'s own serialization boundary, ADR 0015);
Core lets each store method map directly to/from that dict without a
second parallel object model to keep in sync. `brief`,
`generation_job_ids`, `asset_ids`, and `render_manifest` are stored as
`Text` columns holding `json.dumps(...)` output rather than Postgres
`JSONB` - this table is only ever read/written a whole row at a time
through `ProjectRecord`, never queried by a JSON field's contents, so
`JSONB`'s indexing/containment-query features would add complexity this
access pattern never uses.

### 2. `postgresql+psycopg://` (psycopg3), not the bare `postgresql://` (psycopg2) dialect

`packages/persistence` depends on `psycopg[binary]` (psycopg3), not
`psycopg2` - SQLAlchemy's dialect resolution defaults a bare
`postgresql://` URL to psycopg2 and fails with `ModuleNotFoundError`
otherwise (confirmed empirically). `config_sdk.Settings.database_url`'s
default and every doc/`.env.example` reference now use the explicit
`postgresql+psycopg://` scheme.

### 3. `save()` takes `SELECT ... FOR UPDATE` before writing

Directly addresses Risk 2: `save()` locks the target row
(`select(...).where(project_id == ...).with_for_update()`) inside the
same transaction as the subsequent `UPDATE`, so two concurrent `save()`
calls for the same `project_id` serialize on Postgres's own row lock
rather than racing at the application level. `create()` similarly checks
existence and inserts inside one transaction, so
`IProjectStore.create`'s "raises `ValueError` if the id already exists"
contract holds under concurrency the same way it always did for
`InMemoryProjectStore` (single-threaded dict access has no race to begin
with; Postgres needs the explicit lock to get the same guarantee).

### 4. Alembic owns the schema; `PostgresProjectStore.__init__` still calls `metadata.create_all(...)`

`packages/persistence/alembic/` (`alembic.ini` at the package root,
`env.py` reading `target_metadata` from `postgres_store.metadata` and
`DATABASE_URL` if set, else `alembic.ini`'s own default) is the real,
executed migration path - `alembic upgrade head` was run against the
live server and produced the actual `projects` table verified via
`psql \d projects`. `PostgresProjectStore.__init__` also calls
`metadata.create_all(self._engine)` unconditionally: harmless
(`CREATE TABLE IF NOT EXISTS` semantics) against a database Alembic has
already migrated, and it means every test in
`tests/test_postgres_project_store.py` (and any fresh throwaway dev
database) needs zero manual migration step to run. On a database that
already holds real project data, Alembic - not `create_all` - is the
only path for a future schema change (adding a column, etc.).

### 5. `PROJECT_STORE=memory|postgres`, defaulting to `memory` - same swap-point discipline as `ORCHESTRATOR`

`config_sdk.Settings.project_store` (default `"memory"`) selects between
`InMemoryProjectStore` and `PostgresProjectStore` in
`apps/api/state.py`'s `build_app_state()`, mirroring `ORCHESTRATOR`'s own
`sync`/`temporal` swap point (ADR 0015) exactly, including the same
lazy-import discipline (`sqlalchemy`/`psycopg` only imported when
`postgres` is actually selected).

## Consequences

- `tests/test_postgres_project_store.py` is genuinely executed against
  the live local Postgres server (skipped, not failed, when none is
  reachable), covering create/get/save/list, the duplicate-create and
  missing-save error paths, nested JSON round-tripping, and reading a
  row back through a brand-new `PostgresProjectStore`/engine instance to
  prove the data really lives in Postgres and not just in a Python
  object.
- Combined with ADR 0015, `PROJECT_STORE=postgres` +
  `ORCHESTRATOR=temporal` together are what finally let the API process
  and a Temporal worker run as genuinely separate OS processes sharing
  state only through Postgres and the Temporal server - the limitation
  ADR 0015's Consequences section named as WP2's job to fix. This ADR
  does not itself stand up that two-process deployment or add a test for
  it; it only removes the persistence-layer blocker.
- `apps/api`'s default behavior is unchanged - `PROJECT_STORE` defaults
  to `memory`, and every pre-WP2 test/environment is unaffected.
  Selecting `postgres` is opt-in and config-driven.
- `IGenerationJobStore` and `IDirectorMemoryStore` remain in-memory only;
  this ADR scopes to `IProjectStore` alone, matching WP2's own scoping in
  `docs/PHASE8_SCALEOUT_PLAN.md`. Redis-backed caching/session state is
  WP3, not this ADR.
- This ADR does not change `IVideoEngine`, `IComputeProvider`,
  `GenerationPipeline`, `ProjectLifecycle`, or
  `CinematicIntelligenceCoordinator` in any way -
  `PostgresProjectStore` is a new implementation of `IProjectStore`, the
  interface every caller already depended on exclusively.
