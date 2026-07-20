# services/storyboard-generator

## Storyboard Generator

**Responsibility:** Produces a cheap, fast preview of the whole plan - one frame per shot, each with a plain-language description and an optional low-cost preview image - so a human can approve or request changes BEFORE any full-cost video rendering happens. This is the single most important cost-control checkpoint in the pipeline.

**Input:** `scene.schema.json` list (with shots populated by Shot Planner)

**Output:** `storyboard.schema.json`, status starts at `pending_review`

**Consumed by:** Frontend (human approval gate), then Render Configuration Compiler once `status == approved`

**Status:** Interface/package scaffolded in Phase 0. Business logic is a
Phase 2 target - see `docs/ARCHITECTURE.md#roadmap`.
