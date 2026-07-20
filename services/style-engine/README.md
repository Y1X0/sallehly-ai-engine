# services/style-engine

## Style Director (Style Engine)

**Responsibility:** finalizes the DirectorPlan-wide `global_style` once:
a deterministic `consistency_seed` (hashed from `project_id`, so re-runs
are reproducible and engines that support seeding produce visually
related shots), default `color_grade` from keyword rules over
`visual_style`, and a `reference_image_ids` placeholder (populated once
`services/asset-manager` exists, Phase 3). Per-shot overrides remain
possible via `shot.style_override` but are not automatically generated in
Phase 2 - a shot only gets one if something upstream explicitly calls for
a mood shift.

**Input:** `director_plan.global_style` (as set by `CreativeDirector` in Phase 1) + `project_id`

**Output:** the finalized `global_style` (`style.schema.json`)

**Consumed by:** Storyboard Generator, Render Configuration Compiler

## Status (Phase 2)

Implemented as `StyleDirector.finalize_global_style(director_plan)`.
Deterministic - no LLM call needed.
