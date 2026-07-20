# packages/schemas

The single source of truth for every data contract that crosses a module
boundary in this system. Every service reads and writes JSON that validates
against one of these schemas — nothing crosses a boundary as untyped free
text.

## Files (`json/`)

| Schema | Produced by | Consumed by |
|---|---|---|
| `project.schema.json` | API / project service | everything |
| `creative_brief.schema.json` | Creative Brief Parser | Story Planner |
| `story_outline.schema.json` | Story Planner | Scene Generator (Creative Director orchestrates) |
| `director_plan.schema.json` | Creative Director (assembled from `story_outline` + generated scenes/shots) | Prompt Builder, Scene Builder |
| `scene.schema.json` | Scene Builder | Storyboard Generator, Shot Planner |
| `shot.schema.json` | Shot Planner (then enriched by Camera/Motion/Lighting/Style engines) | Render Configuration Compiler |
| `camera.schema.json` | Camera Engine | embedded in `shot`, `render_configuration` |
| `motion.schema.json` | Motion Engine | embedded in `shot` |
| `lighting.schema.json` | Lighting Engine | embedded in `shot`, `render_configuration` |
| `style.schema.json` | Style Engine | embedded in `director_plan` (global) and `shot` (override) |
| `storyboard.schema.json` | Storyboard Generator | Frontend (human approval gate 1) |
| `capability_manifest.schema.json` | Model Registry (per engine) | Render Configuration Compiler |
| `render_configuration.schema.json` | Render Configuration Compiler | Video Engine Adapter (`IVideoEngine.submit`), embedded in `render_plan` |
| `render_plan.schema.json` | Render Configuration Compiler (via `CreativeCompiler`) | Frontend (human approval gate 2), then Render Orchestrator |
| `generation_job.schema.json` | Render Orchestrator (`GenerationPipeline`) | Frontend / API (job status polling) |
| `asset_record.schema.json` | Asset Manager | Render Orchestrator, Frontend/API (asset lookup) |
| `user.schema.json` | Auth (`IAuthProvider.register`) | Frontend/API (`GET /users/me`) |

## Rules

1. **Additive changes only within a major version.** Adding an optional
   field is fine; removing or repurposing a field requires a new
   `schema_version` and a migration note in `docs/adr/`.
2. **No engine-specific or LLM-specific fields** in any schema above
   `render_configuration` and `director_plan.generated_by` respectively.
   If a field only makes sense for one engine or one provider, it does not
   belong in the shared contract — it belongs in that adapter's own
   internal config.
3. Every schema file is standalone-valid JSON Schema (draft 2020-12) and
   uses relative `$ref`s to the other files in this directory so tooling
   can resolve them without a network fetch.

## Language bindings

Phase 0 ships the schemas as the canonical JSON Schema files. Each
Python service generates/uses matching Pydantic models from these files
(see each service's `schemas.py`) rather than hand-maintaining parallel
definitions — the JSON Schema is the source of truth, Pydantic models are
generated or kept in lockstep with it.
