# packages/persistence

`IProjectStore` - the Project persistence entity the API layer reads and
writes (`ProjectRecord`: identity, brief, `ProjectStatus`, and references
into other stores). `InMemoryProjectStore` today; a Postgres-backed
implementation is a later swap behind the same interface.

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

## Status (Phase 4)

`InMemoryProjectStore` implemented and used by `ProjectLifecycle`/
`ProjectOrchestrator` and `apps/api`. A Postgres-backed implementation is
a natural later swap - `docker-compose.yml` already runs Postgres, but no
service has an ORM/session layer wired up yet.
