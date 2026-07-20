# services/shot-planner

## Shot Planner

**Responsibility:** Expands each Scene into an ordered list of Shots: shot type (wide/medium/close/insert/...), duration, and in/out transitions. Does not yet decide camera, motion, lighting, or style - those are filled in by the dedicated engines that run immediately after this one in the pipeline.

**Input:** `scene.schema.json` (summary, characters, continuity_notes)

**Output:** `shot.schema.json` entries (camera/motion/lighting/style fields still null)

**Consumed by:** Camera Engine

**Status:** Interface/package scaffolded in Phase 0. Business logic is a
Phase 2 target - see `docs/ARCHITECTURE.md#roadmap`.
