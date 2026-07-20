# services/render-config-compiler

## Render Configuration Compiler

**Responsibility:** The critical abstraction boundary of the whole system: merges a fully-populated Shot (camera + motion + lighting + style + prompts) with the active engine's CapabilityManifest into one RenderSpec. Clamps/rescales values to what the engine actually supports (e.g. motion_strength range, max shot duration) so nothing upstream needs engine-specific knowledge. Swapping Wan2.1 for a future engine means this module starts reading a different CapabilityManifest - nothing else in services/ changes.

**Input:** `shot.schema.json` (fully populated) + active `capability_manifest.schema.json`

**Output:** `render_configuration.schema.json` (RenderSpec), one per shot

**Consumed by:** Video Engine Adapter, via the Render Orchestrator

**Status:** Interface/package scaffolded in Phase 0. Business logic is a
Phase 2 target - see `docs/ARCHITECTURE.md#roadmap`.
