# services/render-orchestrator

## Render Orchestrator

**Responsibility:** Owns the durable, long-running Temporal workflow that drives a project from approved storyboard to finished shots: for each RenderSpec, calls `IVideoEngine.build_job_payload`, submits it via the configured `IComputeProvider`, polls to completion, retries on transient failure, and hands the resulting RawClip to Post-Processing. See docs/workflows/ai-director-workflow.md.

**Input:** Approved `storyboard.schema.json` + its Shots' `render_configuration.schema.json` entries

**Output:** `RawClip` per shot (from `video_engine_sdk.types`)

**Consumed by:** Post-Processing

**Status:** Interface/package scaffolded in Phase 0. Business logic is a
Phase 4 target - see `docs/ARCHITECTURE.md#roadmap`.
