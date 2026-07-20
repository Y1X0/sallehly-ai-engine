# ADR 0008: Storyboard Generator runs after Camera/Motion/Lighting/Style planning

**Status:** Accepted — supersedes the ordering (not the terminology
mapping) in ADR 0007

## Context

ADR 0007 placed the Storyboard Generator immediately after Shot Planner
and before the Camera/Motion/Lighting/Style Directors, reasoning that it
was the cheapest possible human-approval checkpoint.

Phase 2's requirements make each storyboard frame carry camera framing,
lens choice, camera movement, lighting, environment, mood, and
transition for every shot. Those fields do not exist until the Camera,
Motion, Lighting, and Style Directors have already run - a storyboard
cannot describe "50mm lens, slow dolly-in, golden-hour lighting" before
something has decided that shot uses a 50mm lens, a dolly-in, and
golden-hour lighting.

## Decision

The Storyboard Generator moves to run *after* the four Phase 2 Directors,
not before:

```
DirectorPlan (bare shots, from CreativeDirector, Phase 1)
  -> Style Director     (finalizes global_style once)
  -> Camera Director     (per shot)
  -> Motion Director      (per shot)
  -> Lighting Director     (per shot)
  -> Storyboard Generator   (renders all of the above into readable frames)
       === approval gate 1: storyboard ===
  -> Render Specification Generator
       === approval gate 2: render plan ===
```

This is a **two-gate** model, not the single early gate ADR 0007
described:

- **Gate 1 (storyboard)** is still the primary checkpoint - it catches a
  wrong shot breakdown, camera choice, lighting mood, or pacing. It is no
  longer "before any technical planning" (that planning is now cheap and
  deterministic - no LLM call, see each Director's own README - so there
  is no meaningful cost to run it before the gate).
- **Gate 2 (render plan)**, new in Phase 2, sits after the Render
  Specification Generator and catches anything specific to the
  engine-compiled plan (e.g. a shot split into two parts because it
  exceeded the active engine's `max_shot_duration_sec`). This is the
  last checkpoint before any GPU cost is spent (Phase 3+).

`packages/schemas/json/render_plan.schema.json` was added to give gate 2
a concrete artifact with the same `draft/pending_review/approved/
changes_requested` lifecycle `storyboard.schema.json` already used for
gate 1, rather than inventing a different pattern.

`docs/adr/0007-pipeline-stage-terminology-and-ordering.md`'s terminology
mapping (Director vs. Engine naming) is unaffected and remains accurate.

## Consequences

- `docs/ARCHITECTURE.md`'s pipeline diagram and roadmap reflect this
  order, not ADR 0007's original one.
- Because Camera/Motion/Lighting/Style planning is deterministic (no LLM
  call - see ADR 0007's reasoning, reaffirmed for each Director's actual
  Phase 2 implementation), running it before gate 1 costs essentially
  nothing, so the "avoid spending before human approval" goal ADR 0007
  cared about is preserved - the cost that actually matters (GPU
  rendering) is still gated, now by gate 2.
- `services/creative-compiler`'s `compile_render_plan` refuses to run
  until the referenced storyboard's `status == "approved"`, enforcing
  gate ordering in code, not just in documentation.
