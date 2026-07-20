# ADR 0007: Pipeline stage terminology and ordering reconciliation

**Status:** Accepted

## Context

Phase 1 planning named pipeline stages slightly differently than Phase 0
had, and in a different order:

> User idea → Creative Brief Parser → Story Planner → Storyboard
> Generator → Scene Generator → Shot Planner → Camera Director →
> Lighting Director → Motion Director → Render Specification Generator

Two things in that list don't hold up mechanically:

1. **Storyboard Generator before Scene Generator/Shot Planner** — a
   storyboard needs shots to have frames for. It cannot run before
   scenes and shots exist.
2. **"Director" vs "Engine" suffixes** — Phase 0 named the per-shot
   technical planners `camera-engine`, `motion-engine`,
   `lighting-engine`, `style-engine`; Phase 1 planning called the same
   concepts "Camera Director," "Motion Director," "Lighting Director."

Neither is a substantive disagreement, just an ordering/naming pass that
needed reconciling against what actually has to happen mechanically.

## Decision

**Ordering** (implemented as of Phase 1):

```
User idea
  -> Creative Brief Parser      (LLM)   -- services/creative-brief-parser
  -> Story Planner               (LLM)   -- services/story-planner
  -> Scene Generator          (deterministic) -- services/scene-builder
  -> Shot Planner             (deterministic) -- services/shot-planner
  -> Storyboard Generator     (Phase 2)        -- services/storyboard-generator
       --- human approval gate 1: story/shot breakdown ---
  -> Camera Director          (Phase 2)        -- services/camera-engine
  -> Motion Director          (Phase 2)        -- services/motion-engine
  -> Lighting Director        (Phase 2)        -- services/lighting-engine
  -> Style Director           (Phase 2)        -- services/style-engine
  -> Render Specification Generator (Phase 2) -- services/render-config-compiler
       --- human approval gate 2: full render, optional ---
```

Storyboard Generator moves to immediately after Shot Planner rather than
before it. This is also the *cheapest possible* place for the human
approval gate: it catches a wrong story or shot breakdown before any
per-shot camera/lighting/motion/style planning (Phase 2, potentially
LLM-backed for creative sub-decisions) runs, rather than after.

**Terminology:** "Director" is the product/planning term for the same
services Phase 0 named with an "Engine" suffix. Phase 0's directory names
(`camera-engine`, `motion-engine`, `lighting-engine`, `style-engine`) are
kept as-is to avoid churn on already-committed structure; documentation
(`docs/ARCHITECTURE.md`, each service's own `README.md`) uses "Director"
as the primary product-facing name and notes the directory mapping. No
functional difference either way — this is purely a naming
reconciliation, not a redesign.

"Creative Director" (the orchestrator, `CreativeDirector` class in
`services/ai-director`) and "AI Director" (the layer/concept name used
throughout `docs/ARCHITECTURE.md` and earlier ADRs) refer to the same
thing.

## Consequences

- `docs/workflows/ai-director-workflow.md` and `docs/ARCHITECTURE.md`'s
  pipeline diagram reflect the corrected order, not the originally-listed
  one.
- Anyone reading Phase 1 planning discussion alongside this repo should
  use this ADR as the map between the two namings/orderings — neither
  discussion is "wrong," they were just reconciled here in favor of what
  the schemas' data dependencies actually require.
- No schema, interface, or already-implemented service needed to change
  to accommodate this — `scene.schema.json`, `shot.schema.json`, and
  `storyboard.schema.json` already modeled the corrected order (a
  `Storyboard` frame references a `shot_id`, which only exists after Shot
  Planner runs).
