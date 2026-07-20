# services/shot-planner

## Shot Planner

**Responsibility:** expands each `Scene` into an ordered list of bare
`Shot` entries — shot count, duration, plain-language description, and
in/out transitions, derived heuristically from the scene's estimated
duration. Does not decide camera, motion, lighting, or style — those
fields stay unset here and are filled in by the Camera/Motion/Lighting/
Style Directors in Phase 2.

**Input:** `Scene` (from Scene Generator) + the scene's `estimated_duration_sec` (from `story_outline.scene_skeleton`)

**Output:** `shot.schema.json` entries (camera/motion/lighting/style_override left unset)

**Consumed by:** Camera Director (Phase 2), then `CreativeDirector` assembles the full `director_plan.schema.json`

## Status (Phase 1)

Implemented as `ShotPlanner.plan_shots()` — a duration-budget heuristic
(~3s/shot, rotating through a fixed shot-type sequence via
`default_shot_type()` as a starting point for the future Camera
Director) rather than an LLM call, per
`docs/adr/0007-pipeline-stage-terminology-and-ordering.md`.
