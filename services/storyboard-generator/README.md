# services/storyboard-generator

## Storyboard Generator

**Responsibility:** renders every shot's already-populated camera/motion/
lighting (from the Camera/Motion/Lighting/Style Directors) into a
complete, human-readable storyboard frame - visual description, camera
framing, lens choice, camera movement, lighting, environment, mood, and
transition - for human approval (**gate 1**) before the Render
Specification Generator compiles the final technical plan (**gate 2**,
see `render_plan.schema.json`).

This runs *after* per-shot technical planning, not before - see
`docs/adr/0008-storyboard-after-technical-planning.md` for why (a
storyboard entry describing "50mm lens, dolly-in, golden-hour lighting"
needs those decisions to already exist).

**Input:** `director_plan.schema.json` with every shot's `camera`, `motion`, `lighting` populated

**Output:** `storyboard.schema.json`, `status = "pending_review"`, `director_plan_version` = a content hash of the plan (see `schemas.content_hash`)

**Consumed by:** Frontend / API (human approval gate 1), then the Render Specification Generator once `status == "approved"`

## Status (Phase 2)

Implemented as `StoryboardGenerator.generate(director_plan)`. Purely a
presentation layer over already-decided data - deterministic, no new
creative decisions, no LLM call. `preview_image_asset_id` is left unset
until an image-generation engine exists (Phase 3+; see
`docs/ARCHITECTURE.md`'s forward-compatibility notes on `IImageEngine`).
