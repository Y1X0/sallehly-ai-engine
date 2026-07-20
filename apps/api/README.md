# apps/api

Public/internal API gateway (BFF). Auth, rate limiting, request
validation, and billing metering live here; all creative/rendering logic
lives in `services/*` and is invoked through the Workflow Orchestrator,
never called directly from a route handler.

See `docs/api/openapi.yaml` for the full contract this app implements
against, and `docs/ARCHITECTURE.md` for where this sits in the pipeline.

**Status:** health check only (Phase 0). Route implementation is a
Phase 1+ task, gated on `ai-director` and the creative compiler services
being ready to call.
