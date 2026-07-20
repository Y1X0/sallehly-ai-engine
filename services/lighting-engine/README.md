# services/lighting-engine

## Lighting Director (Lighting Engine)

**Responsibility:** deterministic lighting planning for each shot: infers
a `time_of_day` from the DirectorPlan's global style (keyword rules over
`global_style.visual_style`), then derives mood, key/fill light,
rim-light (for close-ups, to separate subject from background),
volumetric/atmospheric effects, and an advisory `grading_direction`.

`grading_direction` is a hint, not a competing source of truth - the
Style Director owns the final `color_grade` values on the global style
(see `lighting.schema.json`'s field description).

**Input:** `shot.schema.json` + the shot's `camera` (for rim-light decision) + `director_plan.global_style`

**Output:** populates `shot.lighting` (`lighting.schema.json`)

**Consumed by:** Storyboard Generator, Style Director (as a grading hint), Render Configuration Compiler

## Status (Phase 2)

Implemented as `LightingDirector.plan_lighting(shot, camera, global_style)`.
Deterministic keyword-rule inference - no LLM call needed.
