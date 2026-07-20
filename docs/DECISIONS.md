# Decision Log

Chronological record of decisions made during Phase 0/1 planning. Each
non-trivial decision also has a full ADR in `docs/adr/`.

| # | Decision | Rationale (short) | ADR |
|---|---|---|---|
| 1 | AI Director (LLM) and Video Engine are fully separate layers, communicating only via versioned JSON schemas | The entire point of the project: either side must be replaceable without rewriting the other | [0001](adr/0001-director-engine-separation.md) |
| 2 | `IVideoEngine` (which model) and `IComputeProvider` (where it runs) are two separate interfaces, not one | GPU hosting strategy and model choice are independent axes of change | [0002](adr/0002-compute-provider-abstraction.md) |
| 3 | Backend language: Python (FastAPI) across every service | Wan2.1 and its successors are PyTorch; one language end-to-end removes an unnecessary serialization/FFI boundary | [0003](adr/0003-language-python.md) |
| 4 | Workflow engine: Temporal.io, isolated behind Render Orchestrator | Durable execution, retries, and a human-approval signal (storyboard gate) are native to Temporal; isolating it keeps a future swap possible | [0004](adr/0004-workflow-engine-temporal.md) |
| 5 | GPU compute: start on RunPod Serverless + rented Vast.ai instances, not Kubernetes | Lowest cost/complexity for early experiments; Kubernetes is deferred to Phase 7 behind `IComputeProvider` | [0005](adr/0005-gpu-provider-runpod-vastai-first.md) |
| 6 | First Video Engine: Wan2.1 (Apache-2.0), wrapped in `Wan21Adapter` | Supports T2V/I2V/video-edit, runs on consumer/prosumer GPUs, permissive license | (tracked in `models/registry.yaml`) |
| 7 | Repository: `sallehly-ai-video-engine`, fully separate from `sallehly_app` | Independent product, not a feature of the existing Flutter app | — |
| 8 | License for this repository's own code: **not yet decided** | Needs a deliberate choice (MIT/Apache-2.0/proprietary) — flagged for user decision, not assumed | — |
| 9 | Structured output enforcement = Claude forced tool-use + a provider-agnostic `RetryingLLMProvider` decorator | Retry/validation should not be reimplemented per provider; a decorator applies to any `ILLMProvider` uniformly | [0006](adr/0006-structured-output-retry-decorator.md) |
| 10 | Creative Brief Parser and Story Planner are separate services from the Creative Director orchestrator, each with their own `ILLMProvider` dependency and prompt template | Keeps each LLM call and each prompt template independently focused, versioned, and retriable | (see `services/ai-director/README.md`) |
| 11 | Storyboard Generator runs after Shot Planner, not before Scene Generator as originally listed in Phase 1 planning; "Director"/"Engine" naming reconciled | Storyboard frames reference shot ids that don't exist until shots are planned; this is also the cheapest point for the human approval gate | [0007](adr/0007-pipeline-stage-terminology-and-ordering.md) |
| 12 | Storyboard Generator moved again: now runs *after* Camera/Motion/Lighting/Style planning, not before | Phase 2 storyboard frames must describe lens/movement/lighting, which don't exist until those Directors run; this supersedes ADR 0007's ordering (not its terminology mapping) | [0008](adr/0008-storyboard-after-technical-planning.md) |
| 13 | Two approval gates, not one: storyboard (gate 1) and `render_plan.schema.json` (gate 2) | Gate 1 catches a wrong creative/shot plan; gate 2 catches anything specific to the engine-compiled RenderSpecs (e.g. a shot split for exceeding `max_shot_duration_sec`) before any GPU cost is spent | [0008](adr/0008-storyboard-after-technical-planning.md) |
| 14 | Camera/Motion/Lighting/Style Directors and the Render Specification Generator are all deterministic (no LLM call) | Their job is mechanical translation of already-decided creative intent (from the Story Planner) into cinematography/technical parameters - a good fit for rule-based logic, consistent with Scene Generator/Shot Planner's Phase 1 precedent | (see each service's own README) |
| 15 | Prompt composition for `positive_prompt`/`negative_prompt` is currently inline in Render Config Compiler | A dedicated Prompt Builder (prompt-fragment library, per-engine phrasing dialects) wasn't part of Phase 2's scope; a simple deterministic concatenation is enough to produce valid, useful RenderSpecs today | (see `services/render-config-compiler/README.md`) |
| 16 | `GenerationPipeline` (`services/render-orchestrator`) is the sole place a `RenderSpec` dict becomes a concrete engine call | Keeps `CreativeDirector`/`CreativeCompiler` unaware Wan2.1 (or any engine) exists, per ADR 0001; this is where the dict->dataclass `RenderSpec` conversion lives | [0009](adr/0009-generation-pipeline.md) |
| 17 | `GenerationJob` status names (`queued`/`running`/`completed`/`failed`) are distinct from `ComputeJobStatus`'s (`.../succeeded`/`.../cancelled`) | A `GenerationJob` is the platform's business object; `ComputeJobStatus` is a specific compute provider's report - `GenerationPipeline` maps one to the other rather than reusing the same enum for both | [0009](adr/0009-generation-pipeline.md) |
| 18 | RunPod prioritized as the first production-ready `IComputeProvider`; `VastAIProvider` stays a stub | Vast.ai's rented-instance model needs a companion self-hosted job-runner service (`infra/vastai/`) not yet built; RunPod's request/response Serverless API was simpler to productionize first | (see `services/video-engine-adapter/README.md`) |
| 19 | `IStorageProvider` (`packages/storage-sdk`) is separate from `AssetManager`'s registry, and isn't on the Phase 3 critical path | A `RawClip`'s URI already points somewhere valid (compute provider's upload target); `IStorageProvider` is for the platform copying/persisting bytes it owns, needed starting Phase 5 (Post-Processing), not Phase 3 | [0009](adr/0009-generation-pipeline.md) |

## Open decision: repository license

Every dependency this project vendors or wraps (Wan2.1: Apache-2.0) is
tracked in `models/registry.yaml`, but the license for *this repository's
own code* has not been set — no `LICENSE` file is included yet. This is
deliberately left to you: it affects whether the platform itself can be
open-sourced, and picking wrong is hard to undo once external
contributors or customers are depending on a license grant. Decide when
ready and this doc will be updated with the ADR.
