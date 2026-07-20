# services/ai-director

## CreativeDirector — the Creative Director orchestrator

**Responsibility:** the single entry point for turning a raw user idea
into a `DirectorPlan`. It does not do the creative work itself — it
composes four other services in order and assembles their output:

```
ProjectBrief
  -> CreativeBriefParser.parse()          (services/creative-brief-parser, LLM)
  -> StoryPlanner.plan()                  (services/story-planner, LLM)
  -> SceneGenerator.generate_scenes()     (services/scene-builder, deterministic)
  -> ShotPlanner.plan_shots()             (services/shot-planner, deterministic)
  -> CreativeDirector._assemble()         (this service, deterministic merge + schema validation)
  -> DirectorPlan
```

## Interface

```python
from ai_director import CreativeDirector, ProjectBrief
from llm_providers.claude_provider import ClaudeProvider

director = CreativeDirector(llm_provider=ClaudeProvider(api_key=...))
plan = director.generate_director_plan(
    ProjectBrief(
        project_id="proj_123",
        prompt="A 20-second product ad for a minimalist watch brand, warm and premium mood",
        target_duration_sec=20,
        aspect_ratio="16:9",
    )
)
# plan validates against packages/schemas/json/director_plan.schema.json

# Storyboard rejected with feedback:
revised_plan = director.regenerate_with_feedback(
    project_id="proj_123",
    feedback=["Shot 2 feels too static, add camera movement", "Make the tone warmer"],
)
```

## How it stays LLM-agnostic

`CreativeDirector` takes exactly one `ILLMProvider` and wraps it once in
`RetryingLLMProvider` (schema validation + retry-with-feedback, see
`packages/llm-providers`), then hands that same wrapped instance to both
`CreativeBriefParser` and `StoryPlanner`. Swapping Claude for another
provider means constructing `CreativeDirector` with a different
`ILLMProvider` — nothing else in this service, or in the two LLM-backed
services it composes, changes.

## Memory

`CreativeDirector` owns an `IDirectorMemoryStore`
(`packages/director-memory`, defaulting to `InMemoryDirectorMemoryStore`)
and records every `CreativeBrief`, `StoryOutline`, `DirectorPlan`, and
piece of reviewer feedback per project. This is what makes
`regenerate_with_feedback` possible without re-parsing the original idea.

## Inputs / Outputs

| | Schema |
|---|---|
| Input | `project.schema.json` → `.brief` (wrapped as `ProjectBrief`) |
| Intermediate | `creative_brief.schema.json`, `story_outline.schema.json` (not exposed outside this pipeline) |
| Output | `director_plan.schema.json` |

## Downstream consumers

`services/render-config-compiler` (Phase 2) and the Camera/Motion/
Lighting/Style Directors (Phase 2) consume the `DirectorPlan` this
service produces. None of them call back into `CreativeDirector`
mid-pipeline.

## Status (Phase 1)

Fully implemented and unit-tested end-to-end against a `FakeLLMProvider`
(see `tests/test_creative_pipeline.py`). The only piece requiring a real
API key to exercise is `ClaudeProvider.generate_structured` itself
(`packages/llm-providers/src/llm_providers/claude_provider.py`), which is
implemented but untested against the live Claude API in this
environment.

See `docs/adr/0007-pipeline-stage-terminology-and-ordering.md` for why
the pipeline is ordered this way and how it maps to the stage names used
in product discussions (Story Planner, Camera Director, etc.).
