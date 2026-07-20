# Decision Log

Chronological record of decisions made during Phase 0 planning. Each
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

## Open decision: repository license

Every dependency this project vendors or wraps (Wan2.1: Apache-2.0) is
tracked in `models/registry.yaml`, but the license for *this repository's
own code* has not been set — no `LICENSE` file is included yet. This is
deliberately left to you: it affects whether the platform itself can be
open-sourced, and picking wrong is hard to undo once external
contributors or customers are depending on a license grant. Decide when
ready and this doc will be updated with the ADR.
