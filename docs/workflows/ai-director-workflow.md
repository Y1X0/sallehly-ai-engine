# AI Director / Render Workflow

Owned by `services/render-orchestrator`, implemented as a Temporal
workflow (see ADR 0004). This is the single durable process that carries
one project from a submitted brief to a finished export. As of Phase 2,
everything up to and including both approval gates is implemented and
tested outside of Temporal (`tests/test_creative_pipeline.py`,
`tests/test_creative_compiler.py`); this document describes how the
still-unbuilt Render Orchestrator (Phase 4) will drive those already-real
components.

## Workflow steps

```mermaid
sequenceDiagram
    participant API as apps/api
    participant WF as Render Orchestrator (Temporal Workflow)
    participant DIR as CreativeDirector<br/>(Brief Parser -> Story Planner -> Scene Generator -> Shot Planner)
    participant CC as CreativeCompiler<br/>(Style/Camera/Motion/Lighting Directors -> Storyboard -> Render Spec Generator)
    participant ENG as IVideoEngine (Wan21Adapter)
    participant CMP as IComputeProvider (RunPod/Vast.ai)
    participant PP as Post-Processing
    participant EXP as Export Service

    API->>WF: StartRenderWorkflow(ProjectBrief)
    WF->>DIR: generate_director_plan(brief)
    Note over DIR: internally: CreativeBriefParser -> StoryPlanner -><br/>SceneGenerator -> ShotPlanner (Phase 1)
    DIR-->>WF: DirectorPlan (scenes + bare shots)

    WF->>CC: compile_storyboard(director_plan)
    Note over CC: internally: StyleDirector -> per-shot Camera/Motion/Lighting<br/>Directors -> StoryboardGenerator (Phase 2)
    CC-->>WF: (enriched DirectorPlan, Storyboard)
    WF->>API: notify - awaiting gate 1 (storyboard)
    Note over WF: Workflow blocks on a Temporal signal here.
    API-->>WF: signal: storyboard_approved (or changes_requested)

    alt changes_requested
        WF->>DIR: regenerate_with_feedback(project_id, feedback)
        Note over WF: loops back to compile_storyboard with the revised plan
    else approved
        WF->>CC: approve_storyboard(project_id, storyboard)
        WF->>CC: compile_render_plan(project_id)
        Note over CC: RenderConfigCompiler reads the active engine's<br/>CapabilityManifest - clamps/splits/rescales per shot
        CC-->>WF: RenderPlan (status=pending_review)
        WF->>API: notify - awaiting gate 2 (render plan)
        Note over WF: Workflow blocks on a second Temporal signal here.
        API-->>WF: signal: render_plan_approved (or changes_requested)

        alt changes_requested
            WF->>CC: compile_render_plan(project_id) again after upstream fixes
        else approved
            WF->>CC: approve_render_plan(project_id, render_plan)
            loop for each RenderSpec in render_plan.render_specs
                WF->>ENG: build_job_payload(spec)
                ENG-->>WF: EngineJobPayload
                WF->>CMP: submit(payload)
                CMP-->>WF: ComputeJobHandle
                WF->>CMP: get_status(handle) (polled activity, retried on failure)
                CMP-->>WF: succeeded
                WF->>CMP: fetch_output(handle)
                CMP-->>WF: EngineJobOutput
                WF->>ENG: parse_result(spec, output)
                ENG-->>WF: RawClip
            end
            WF->>PP: assemble(RawClip[])
            PP-->>WF: master video
            WF->>EXP: export(master)
            EXP-->>WF: final asset URLs
            WF->>API: notify - project.export.ready
        end
    end
```

## Why this is a Temporal workflow and not a simple task queue

- **Durability:** a render can take minutes; if a worker process
  restarts mid-poll, Temporal resumes exactly where it left off.
- **Both approval gates are first-class waits, not poll loops.** The
  workflow blocks on `storyboard_approved`/`changes_requested` and later
  `render_plan_approved`/`changes_requested` signals from `apps/api`
  endpoints (see `docs/api/openapi.yaml` - gate 2's endpoints are a
  Phase 3/4 addition to that contract) for as long as it takes a human to
  respond - hours or days, not just seconds.
- **Per-shot retry policy:** a transient RunPod/Vast.ai failure retries
  that one shot's activity, not the whole project.

## Cost control built into this flow

Camera/Motion/Lighting/Style planning and the Storyboard Generator are
all deterministic (no LLM call, see ADR 0007/0008), so gate 1 costs
essentially nothing to reach. Gate 2 (render plan) is the last checkpoint
before any GPU cost is spent - `RenderSpec.quality_tier` (see
`packages/schemas/json/render_configuration.schema.json`) additionally
allows a cheap/fast `"preview"` render tier if a visual preview is wanted
before committing to `"final"` quality.

## Swap points touched by this workflow

Per ADR 0001/0002, this workflow's activities call `ILLMProvider` (via
`CreativeDirector`), `IVideoEngine`, and `IComputeProvider` purely through
their interfaces. The workflow definition itself never imports Claude,
Wan2.1, RunPod, or Vast.ai specifics - only `services/ai-director`,
`services/creative-compiler`, and `services/video-engine-adapter` do.
