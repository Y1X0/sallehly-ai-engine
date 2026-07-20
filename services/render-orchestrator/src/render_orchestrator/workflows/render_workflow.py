"""Temporal workflow definition. See docs/workflows/ai-director-workflow.md
for the full sequence diagram and rationale (ADR 0004).

This is the only file in the entire codebase allowed to import the
Temporal SDK - every activity it calls out to talks to CreativeDirector,
the Creative Compiler services, IVideoEngine, and IComputeProvider
purely through their existing interfaces.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RenderWorkflowInput:
    project_id: str


class RenderWorkflow:
    """Temporal workflow skeleton - see docs/workflows/ai-director-workflow.md.

    Steps (each a Temporal activity, not implemented here):
      1. generate_director_plan(brief) -> DirectorPlan
      2. compile_shots(plan) -> Shot[] (Scene/Shot/Camera/Motion/Lighting/Style)
      3. generate_storyboard(shots, quality_tier=preview) -> Storyboard
      4. await signal: storyboard_approved | changes_requested
      5. (if approved) compile_render_specs(shots, quality_tier=final) -> RenderSpec[]
      6. for each RenderSpec: submit_and_await_render(spec) -> RawClip
      7. post_process(clips) -> master video
      8. export(master) -> final asset URLs
    """

    async def run(self, workflow_input: RenderWorkflowInput) -> None:
        raise NotImplementedError(
            "Phase 4: implement as a @workflow.defn class per the Temporal "
            "Python SDK, with each numbered step above as a separate "
            "@activity.defn function so retries apply per-step, and a "
            "@workflow.signal for storyboard_approved / changes_requested."
        )
