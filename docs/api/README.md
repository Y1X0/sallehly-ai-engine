# docs/api

`openapi.yaml` is the authoritative public/internal API contract - as of
Phase 4, every path in it is a real, implemented, tested route (see
`apps/api/src/api/routes/`). It references the canonical schemas in
`packages/schemas/json/` directly by relative `$ref` rather than
duplicating their definitions — the request/response bodies for Project,
GenerationJob, and AssetRecord are always exactly the pipeline's internal
contracts, never a hand-maintained API-only shape that can drift.

Note that `project.schema.json` mirrors `persistence.ProjectRecord`
exactly (references into `IGenerationJobStore`/`AssetManager` via
`generation_job_ids`/`asset_ids`, not embedded DirectorPlan/Storyboard
bodies) — see `docs/adr/0010-persistence-and-lifecycle.md` for why.

## Webhooks (Phase 5+, documented here for forward reference)

Once the Export Service exists, completed projects notify a configured
webhook URL with an event shaped like:

```json
{
  "event": "project.export.ready",
  "project_id": "proj_123",
  "assets": [{ "format": "mp4_h264", "url": "https://cdn.../final.mp4" }]
}
```

Not yet part of `openapi.yaml`'s formal contract (OpenAPI 3.1 webhook
support will be added alongside `services/export-service` in Phase 5).
