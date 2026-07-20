# services/scene-builder

## Scene Generator (Scene Analyzer / Scene Builder)

**Responsibility:** expands a `StoryOutline`'s `scene_skeleton` into full
`Scene` entries — carrying over each scene's summary, location, and the
`StoryOutline`'s continuity anchors (recurring characters) and style
hint — without shots yet. Shots are filled in immediately afterward by
the Shot Planner, in the same `CreativeDirector` orchestration pass.

**Input:** `story_outline.schema.json` (`scene_skeleton`, `continuity_anchors`, `global_style_hint`)

**Output:** `scene.schema.json` entries (`shots: []`, populated next by Shot Planner)

**Consumed by:** Shot Planner, then `CreativeDirector` assembles the result into `director_plan.schema.json`

## Status (Phase 1)

Implemented as `SceneGenerator.generate_scenes()` — deterministic (see
`docs/adr/0007-pipeline-stage-terminology-and-ordering.md`): scene
structure follows directly from what the Story Planner already decided,
so no additional LLM call is needed here.
