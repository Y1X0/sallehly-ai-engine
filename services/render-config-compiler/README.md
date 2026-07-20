# services/render-config-compiler

## Render Specification Generator (Render Configuration Compiler)

**Responsibility:** the critical abstraction boundary of the whole
system. Converts a fully-planned `DirectorPlan` (every shot's `camera`/
`motion`/`lighting` populated by the Phase 2 Directors) into a list of
engine-agnostic `RenderSpec`s, reading a `CapabilityManifest`
(`packages/video-engine-sdk`) to:

- pick a supported `resolution` closest to the requested `aspect_ratio`
- clamp/**split** any shot whose `duration_sec` exceeds
  `capability_manifest.max_shot_duration_sec` into multiple sub-shots
  (`{shot_id}_part1`, `{shot_id}_part2`, ...)
- rescale `motion.motion_strength` (0-100 normalized) into the engine's
  actual `motion_strength_range`
- decide `text_to_video` vs `image_to_video` mode from whether the shot
  has `asset_references` *and* the engine supports that mode
- compose `positive_prompt`/`negative_prompt` (a simple deterministic
  concatenation of the shot's description + camera/lighting/style
  summary for now - a dedicated Prompt Builder with a prompt-fragment
  library and per-engine phrasing dialects remains a documented future
  enhancement, not built in Phase 2)
- attach `seed` (from the global style's `consistency_seed` + a running
  shot index, for reproducible-but-varied results) only if the engine
  supports seeding

**Never imports a specific engine adapter.** It is unit-tested entirely
against a hand-built test `CapabilityManifest` (see
`tests/test_creative_compiler.py`) - Wan2.1 is not connected until
Phase 3.

**Input:** `director_plan.schema.json` (every shot fully planned) + a `CapabilityManifest`

**Output:** `render_configuration.schema.json` entries, one or more per shot

**Consumed by:** `services/creative-compiler` (wraps the output in a `render_plan.schema.json` for approval gate 2), then the Video Engine Adapter via the Render Orchestrator (Phase 3/4)

## Status (Phase 2)

Implemented as `RenderConfigCompiler.compile(director_plan, capability_manifest, quality_tier="final")`.
Deterministic - no LLM call.
