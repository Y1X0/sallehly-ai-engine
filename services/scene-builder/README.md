# services/scene-builder

## Scene Analyzer / Scene Builder

**Responsibility:** Breaks a DirectorPlan's logline into an ordered list of Scenes, allocates each scene's share of the target_duration_sec budget, and tracks continuity (recurring characters, locations, lighting mood) so later engines don't have to re-derive it per shot.

**Input:** `director_plan.schema.json` (logline, target_duration_sec, continuity_notes)

**Output:** `scene.schema.json` entries (without shots populated yet)

**Consumed by:** Shot Planner

**Status:** Interface/package scaffolded in Phase 0. Business logic is a
Phase 2 target - see `docs/ARCHITECTURE.md#roadmap`.
