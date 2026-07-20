# AI Director / Render Workflow

Owned by `services/render-orchestrator`, implemented as a Temporal
workflow (see ADR 0004). This is the single durable process that carries
one project from a submitted brief to a finished export.

## Workflow steps

```mermaid
sequenceDiagram
    participant API as apps/api
    participant WF as Render Orchestrator (Temporal Workflow)
    participant DIR as AI Director
    participant CC as Creative Compiler<br/>(Scene/Shot/Camera/Motion/Lighting/Style/RenderConfig)
    participant SBG as Storyboard Generator
    participant ENG as IVideoEngine (Wan21Adapter)
    participant CMP as IComputeProvider (RunPod/Vast.ai)
    participant PP as Post-Processing
    participant EXP as Export Service

    API->>WF: StartRenderWorkflow(ProjectBrief)
    WF->>DIR: generate_director_plan(brief)
    DIR-->>WF: DirectorPlan
    WF->>CC: compile scenes -> shots (camera/motion/lighting/style)
    CC-->>WF: Shot[] fully populated
    WF->>SBG: generate storyboard (preview quality)
    SBG-->>WF: Storyboard (status=pending_review)
    WF->>API: notify - awaiting human approval
    Note over WF: Workflow blocks on a Temporal signal here.
    API-->>WF: signal: storyboard_approved (or changes_requested)
    alt changes_requested
        WF->>DIR: regenerate with feedback
        Note over WF: loops back to compile+storyboard
    else approved
        WF->>CC: compile final RenderSpec per shot (quality_tier=final)
        loop for each shot
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
```

## Why this is a Temporal workflow and not a simple task queue

- **Durability:** a render can take minutes; if a worker process
  restarts mid-poll, Temporal resumes exactly where it left off.
- **The human approval gate is a first-class wait, not a poll loop.**
  The workflow blocks on `storyboard_approved` / `changes_requested`
  signals from `apps/api`'s
  `POST /projects/{id}/storyboard/approve` and
  `POST /projects/{id}/storyboard/request-changes` endpoints
  (see `docs/api/openapi.yaml`) for as long as it takes a human to
  respond — hours or days, not just seconds.
- **Per-shot retry policy:** a transient RunPod/Vast.ai failure retries
  that one shot's activity, not the whole project.

## Cost control built into this flow

The Storyboard Generator step runs *before* any full-cost render, and
uses `quality_tier=preview` in any `RenderSpec` it needs for preview
imagery. Nothing expensive happens until a human explicitly approves —
this is the same `RenderSpec.quality_tier` mechanism documented in
`packages/schemas/json/render_configuration.schema.json`.

## Swap points touched by this workflow

Per ADR 0001/0002, this workflow's activities call `ILLMProvider` (via
`AIDirector`), `IVideoEngine`, and `IComputeProvider` purely through their
interfaces. The workflow definition itself never imports Claude, Wan2.1,
RunPod, or Vast.ai specifics — only `services/ai-director` and
`services/video-engine-adapter` do.
