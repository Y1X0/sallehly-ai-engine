# services/prompt-builder

## Prompt Builder

**Responsibility:** Converts DirectorPlan creative intent into engine-ready prompt text: a PositivePrompt and NegativePrompt per shot, in whichever phrasing dialect the active Video Engine's CapabilityManifest expects. Draws on the Prompt Library (reusable, versioned prompt fragments) and Template Library (full DirectorPlan templates for common video genres) to keep quality consistent.

**Input:** `director_plan.schema.json` (a Scene/Shot at a time) + entries from `libraries/prompt-library`

**Output:** `positive_prompt` / `negative_prompt` strings attached to each Shot before Render Configuration Compiler runs

**Consumed by:** Render Configuration Compiler

**Status:** Interface/package scaffolded in Phase 0. Business logic is a
Phase 2 target - see `docs/ARCHITECTURE.md#roadmap`.
