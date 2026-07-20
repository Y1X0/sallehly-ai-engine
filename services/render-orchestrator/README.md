# services/render-orchestrator

## GenerationPipeline (Phase 3) + Render Orchestrator (Phase 4)

**Responsibility:** drives an approved `RenderPlan`
(`render_plan.schema.json`) to finished shots: for each `RenderSpec`,
converts it to the `video_engine_sdk.types.RenderSpec` dataclass, calls
`IVideoEngine.build_job_payload`, submits via the configured
`IComputeProvider`, polls to completion, retries on failure, hands the
result to `AssetManager`, and tracks every step as a `GenerationJob`
(`generation_job.schema.json`) with a `queued -> running -> completed`/
`failed` lifecycle.

**Input:** an approved `render_plan.schema.json` (or an individual `render_configuration.schema.json` entry)

**Output:** a `GenerationJob` per shot, each pointing at an `asset_record.schema.json` on success

**Consumed by:** Post-Processing (Phase 5, via each job's `output_asset_id`)

## Two layers, added in two phases

- **`GenerationPipeline` (`pipeline.py`) - Phase 3, implemented.** Plain,
  synchronous Python: submit, poll (blocking loop), fetch, retry up to
  `max_retries`. Fully testable today with `LocalProvider` (no GPU) or a
  mocked `RunPodProvider` (`httpx.MockTransport`).
- **Temporal workflow (`workflows/render_workflow.py`) - Phase 4, not yet
  implemented.** Wraps this same logic in Temporal activities for
  durability (survives process restarts) and turns the human approval
  gates into proper signals instead of a caller blocking on a Python
  call. The business logic in `pipeline.py` does not change - Temporal
  activities call it, they don't reimplement it.

## Interface

```python
from render_orchestrator import GenerationPipeline
from video_engine_adapter.adapters import Wan21Adapter
from video_engine_adapter.compute import LocalProvider  # or RunPodProvider

pipeline = GenerationPipeline(
    engine=Wan21Adapter(),
    compute_provider=LocalProvider(),
)
jobs = pipeline.generate_plan(approved_render_plan)  # one GenerationJob per shot
```

Neither this class nor anything above it in the call stack (`CreativeCompiler`,
`CreativeDirector`) is coupled to Wan2.1 specifically - swap the `engine`/
`compute_provider` constructor arguments for a future custom model or a
different GPU provider and nothing else changes. See
`docs/adr/0009-generation-pipeline.md`.

## Status (Phase 3)

`GenerationPipeline`, `GenerationJob`/`IGenerationJobStore` implemented
and tested (`tests/test_generation_pipeline.py`) against `LocalProvider`,
including forced-failure/retry paths. `workflows/render_workflow.py`
remains a Phase 4 target.
