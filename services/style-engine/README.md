# services/style-engine

## Style Engine (Style Planner)

**Responsibility:** Sets the DirectorPlan-wide `global_style` once (visual style, color grade, a shared consistency seed / style embedding) and applies per-shot overrides only where the brief explicitly calls for a shift - this is what keeps a multi-shot video from looking like disconnected clips.

**Input:** `director_plan.global_style` + per-shot description

**Output:** `style.schema.json`, either global (on DirectorPlan) or override (on a Shot)

**Consumed by:** Render Configuration Compiler

**Status:** Interface/package scaffolded in Phase 0. Business logic is a
Phase 2 target - see `docs/ARCHITECTURE.md#roadmap`.
