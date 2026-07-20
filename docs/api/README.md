# docs/api

`openapi.yaml` is the authoritative public/internal API contract. It
references the canonical schemas in `packages/schemas/json/` directly by
relative `$ref` rather than duplicating their definitions — the request/
response bodies for Project, DirectorPlan, and Storyboard are always
exactly the pipeline's internal contracts, never a hand-maintained
API-only shape that can drift.

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
