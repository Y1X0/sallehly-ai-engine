# packages/persistence

`IProjectStore` - the Project persistence entity the API layer reads and
writes (`ProjectRecord`: identity, brief, `ProjectStatus`, and references
into other stores). Two implementations behind the same interface,
selected via `Settings.project_store` (`"memory"` default / `"postgres"`,
`apps/api/state.py`):

- **`InMemoryProjectStore`**: process-local dict. The default for every
  test in this repo and for local dev with no database running.
- **`PostgresProjectStore`** (Phase 8 WP2, `postgres_store.py`): a real
  Postgres table via SQLAlchemy Core, with `SELECT ... FOR UPDATE` in
  `save()` to serialize concurrent writers to the same project row. See
  `docs/adr/0016-postgres-persistence.md`.

## Why only Project has a new store here

Phase 4 asks for database abstractions covering Project, DirectorPlan,
Storyboard, RenderSpec, GenerationJob, and Asset. Five of those six
already have interface-based, replaceable persistence from earlier
phases:

| Entity | Existing store | Since |
|---|---|---|
| DirectorPlan / Storyboard / RenderPlan (RenderSpecs) | `IDirectorMemoryStore` (`packages/director-memory`) | Phase 1 |
| GenerationJob | `IGenerationJobStore` (`services/render-orchestrator`) | Phase 3 |
| Asset | `AssetManager` (`services/asset-manager`) | Phase 3 |

Building six repositories would duplicate three that already work and
follow this exact pattern. `ProjectRecord` is the one genuinely new
entity: nothing previously persisted a top-level Project (id, brief,
lifecycle status) tying a request to everything else. See
`docs/adr/0010-persistence-and-lifecycle.md`.

## Interface

```
IProjectStore.create(ProjectRecord) -> None      # raises if project_id exists
IProjectStore.get(project_id) -> ProjectRecord | None
IProjectStore.save(record) -> None                # update, bumps updated_at
IProjectStore.list_for_workspace(workspace_id) -> list[ProjectRecord]
```

## Migrations

`alembic/` (Alembic, `alembic.ini` at this package's root) owns the
`projects` table schema for `PostgresProjectStore`. Run
`uv run --package persistence alembic -c packages/persistence/alembic.ini upgrade head`
(or `cd packages/persistence && uv run alembic upgrade head`) against a
running Postgres server - `DATABASE_URL` env var overrides
`alembic.ini`'s default if set. `PostgresProjectStore.__init__` also
calls `metadata.create_all(...)` as a convenience for tests/fresh dev
databases; Alembic remains the source of truth for schema changes on a
database that already has data.

## Status (Phase 8)

`InMemoryProjectStore` (Phase 4) and `PostgresProjectStore` (Phase 8
WP2) are both implemented and tested; either can back `ProjectLifecycle`/
`ProjectOrchestrator` and `apps/api` via `PROJECT_STORE=memory|postgres`.
`PostgresProjectStore` is tested against a real local Postgres server
(`tests/test_postgres_project_store.py`) - see
`docs/adr/0016-postgres-persistence.md`.
