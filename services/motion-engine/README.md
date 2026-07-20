# services/motion-engine

## Motion Engine (Motion Planner)

**Responsibility:** Defines subject motion (independent of camera movement): what moves in the frame, how strongly, and any speed-ramp/slow-motion keyframes. Outputs a normalized 0-100 `motion_strength` that the Render Configuration Compiler later rescales into whatever range the active engine's CapabilityManifest declares.

**Input:** `shot.schema.json` (description, camera)

**Output:** Populates `shot.motion` (`motion.schema.json`)

**Consumed by:** Lighting Engine

**Status:** Interface/package scaffolded in Phase 0. Business logic is a
Phase 2 target - see `docs/ARCHITECTURE.md#roadmap`.
