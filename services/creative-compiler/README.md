# services/creative-compiler

## CreativeCompiler — the Phase 2 orchestrator

**Responsibility:** the single entry point for turning a Phase 1
`DirectorPlan` (bare shots - no camera/motion/lighting yet) into an
approved, engine-agnostic `RenderPlan`, ready for a Video Engine Adapter.
Composes six other services in order:

```
DirectorPlan (bare shots)
  -> StyleDirector.finalize_global_style()          (services/style-engine)
  -> per shot: CameraDirector.plan_camera()          (services/camera-engine)
  -> per shot: MotionDirector.plan_motion()          (services/motion-engine)
  -> per shot: LightingDirector.plan_lighting()      (services/lighting-engine)
  -> StoryboardGenerator.generate()                  (services/storyboard-generator)
       === approval gate 1: storyboard ===
  -> RenderConfigCompiler.compile()                  (services/render-config-compiler)
       === approval gate 2: render plan ===
```

## Interface

```python
from creative_compiler import CreativeCompiler
from video_engine_sdk import CapabilityManifest

manifest = CapabilityManifest(engine_id="wan2.1", engine_version="2.1.0", ...)
compiler = CreativeCompiler(capability_manifest=manifest)

enriched_plan, storyboard = compiler.compile_storyboard(director_plan)
# ... human reviews `storyboard` ...
approved_storyboard = compiler.approve_storyboard(director_plan["project_id"], storyboard)

render_plan = compiler.compile_render_plan(director_plan["project_id"])
# ... human reviews `render_plan` ...
approved_render_plan = compiler.approve_render_plan(director_plan["project_id"], render_plan)
# approved_render_plan["render_specs"] is ready for a Video Engine Adapter (Phase 3)
```

## Two approval gates, not one

- **Gate 1 (`storyboard.status`)**: catches a wrong shot breakdown,
  camera choice, lighting mood, or pacing before the final technical
  plan is compiled.
- **Gate 2 (`render_plan.status`)**: catches anything specific to the
  *engine-compiled* plan - e.g. a shot that got split into two parts
  because it exceeded the active engine's `max_shot_duration_sec`, or a
  prompt that reads oddly once assembled - before any GPU cost is spent
  (Phase 3+).

`compile_render_plan` refuses to run until the referenced storyboard's
`status == "approved"`, enforcing the gate order.

## What this class does *not* do

It does not re-plan automatically after `changes_requested` feedback -
recording the rejection and feedback is as far as this class goes. Wiring
"rejected -> go back to CreativeDirector.regenerate_with_feedback -> re-run
compile_storyboard" is an orchestration/retry-loop concern that belongs
to the Render Orchestrator (Phase 4, Temporal workflow - see
`docs/workflows/ai-director-workflow.md`), not this class.

It also never imports a specific engine adapter - `capability_manifest`
is passed in by the caller, so this class works identically for Wan2.1,
a future custom foundation model, or a hand-built test manifest. See
`docs/adr/0001-director-engine-separation.md` and
`docs/adr/0002-compute-provider-abstraction.md`.

## Status (Phase 2)

Fully implemented and tested end-to-end, from a `FakeLLMProvider`-driven
`CreativeDirector` output through both approval gates, in
`tests/test_creative_compiler.py`.
