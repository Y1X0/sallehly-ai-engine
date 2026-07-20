# services/lighting-engine

## Lighting Engine (Lighting Planner)

**Responsibility:** Defines the lighting setup for each shot: time of day, mood, key/fill/rim light direction and hardness, and any HDRI/environment reference - kept consistent within a scene and deliberately evolved across scenes only when the story calls for a mood shift.

**Input:** `shot.schema.json` + `scene.continuity_notes`

**Output:** Populates `shot.lighting` (`lighting.schema.json`)

**Consumed by:** Style Engine

**Status:** Interface/package scaffolded in Phase 0. Business logic is a
Phase 2 target - see `docs/ARCHITECTURE.md#roadmap`.
