# services/motion-engine

## Motion Director (Motion Engine)

**Responsibility:** deterministic subject-motion planning: how strongly
the subject moves (normalized `motion_strength`, 0-100) and a short
description of that motion, keyed off the shot type the Camera Director
already chose. Its `easing_curve` mirrors the shot's
`camera.movement.easing` by default, keeping subject motion and camera
motion feeling consistent within a shot while remaining a distinct value
in the schema (a shot could deliberately diverge them later).

Owns subject motion only - camera motion itself belongs to
`camera.schema.json` (Camera Director).

**Input:** `shot.schema.json` + the shot's already-populated `camera` (`camera.schema.json`)

**Output:** populates `shot.motion` (`motion.schema.json`)

**Consumed by:** Lighting Director, Storyboard Generator, Render Configuration Compiler (rescales `motion_strength` into the active engine's range)

## Status (Phase 2)

Implemented as `MotionDirector.plan_motion(shot, camera)`. Deterministic
by design (see `docs/adr/0007-pipeline-stage-terminology-and-ordering.md`)
- no LLM call needed once shot type is known.
