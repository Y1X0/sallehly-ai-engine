# services/ai-director

**Responsibility:** turn a `ProjectBrief` into a `DirectorPlan` — nothing
else. This service does not know Wan2.1 exists.

## Interface

```python
director = AIDirector(llm_provider=ClaudeProvider(api_key=...))
plan = director.generate_director_plan(
    ProjectBrief(
        project_id="proj_123",
        prompt="A 20-second product ad for a minimalist watch brand, warm and premium mood",
        target_duration_sec=20,
        aspect_ratio="16:9",
    )
)
# plan validates against packages/schemas/json/director_plan.schema.json
```

## How it stays LLM-agnostic

`AIDirector` depends only on `ILLMProvider` (from `packages/llm-providers`).
It builds a system prompt (`prompts.py`) and a JSON Schema
(`packages/schemas/json/director_plan.schema.json`), hands both to
whichever provider is injected, and validates the result itself with
`jsonschema` before returning it — so even a provider with weaker
structured-output guarantees than Claude still gets caught at this
boundary rather than silently corrupting everything downstream.

## Inputs / Outputs

| | Schema |
|---|---|
| Input | `project.schema.json` → `.brief` (wrapped as `ProjectBrief`) |
| Output | `director_plan.schema.json` |

## Downstream consumers

`services/prompt-builder` and `services/scene-builder` are the only
direct consumers of `DirectorPlan`. Neither of them, nor anything further
down the pipeline, is allowed to call back into `AIDirector` mid-pipeline
— if a Planner needs an LLM-backed creative sub-decision (e.g. "suggest 3
alternate taglines for this shot"), it takes its own `ILLMProvider`
dependency directly rather than routing through this service, keeping
`AIDirector` a single, testable entry point for the one contract that
matters: brief in, `DirectorPlan` out.

## Status (Phase 0)

Fully wired except the concrete `ILLMProvider` implementation
(`ClaudeProvider.generate_structured`, see
`packages/llm-providers/src/llm_providers/claude_provider.py`), which is
a Phase 1 task.
