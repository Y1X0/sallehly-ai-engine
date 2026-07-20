# services/story-planner

## Story Planner

**Responsibility:** second stage of the Creative Director pipeline.
Turns a `CreativeBrief` into a narrative arc (ordered story beats) and a
lightweight scene skeleton (order, narrative role, summary, estimated
duration) that sums to the requested `target_duration_sec`. Does not
decide shots, camera, lighting, motion, or style — those belong to Scene
Generator, Shot Planner, and the Camera/Lighting/Motion/Style Directors
that run after it.

**Input:** `creative_brief.schema.json`

**Output:** `story_outline.schema.json`

**Consumed by:** Scene Generator (`services/scene-builder`), via
`CreativeDirector` orchestration

## Revision path

When a storyboard built from this outline gets `changes_requested`
feedback (see `docs/workflows/ai-director-workflow.md`),
`CreativeDirector.regenerate_with_feedback` calls `plan(...)` again with
`feedback` and `prior_story_outline` set, using
`packages/director-memory` to retrieve the prior `CreativeBrief`/
`StoryOutline` for this project. The prompt template
(`libraries/prompt-templates/story_planner/v1.yaml`) has a dedicated
branch for this case, asking for a *targeted* revision rather than a
fresh outline.

## Status (Phase 1)

Implemented, including the revision path's template branch.
