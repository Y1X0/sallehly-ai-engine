# Module Index

Every module's authoritative documentation lives in its own directory as
`README.md` — responsibility, input/output schemas, consumers, and
status. This page is just an index; see `docs/ARCHITECTURE.md#4-module-responsibilities`
for the same list with paths.

## Creative Director (implemented, Phase 1)

- [CreativeDirector orchestrator](../../services/ai-director/README.md)
- [Creative Brief Parser](../../services/creative-brief-parser/README.md)
- [Story Planner](../../services/story-planner/README.md)
- [Scene Generator](../../services/scene-builder/README.md)
- [Shot Planner](../../services/shot-planner/README.md)

## Creative Compiler (implemented, Phase 2)

- [CreativeCompiler orchestrator](../../services/creative-compiler/README.md)
- [Style Director](../../services/style-engine/README.md)
- [Camera Director](../../services/camera-engine/README.md)
- [Motion Director](../../services/motion-engine/README.md)
- [Lighting Director](../../services/lighting-engine/README.md)
- [Storyboard Generator](../../services/storyboard-generator/README.md)
- [Render Specification Generator](../../services/render-config-compiler/README.md)
- [Prompt Builder](../../services/prompt-builder/README.md) *(not started - prompt composition is currently inline in Render Config Compiler)*

## Execution Layer (implemented, Phase 3-4)

- [Video Engine Adapter (Wan2.1 + RunPod)](../../services/video-engine-adapter/README.md)
- [GenerationPipeline + ProjectLifecycle + Temporal workflow](../../services/render-orchestrator/README.md)
- [GPU Worker](../../workers/gpu-worker/README.md) *(container structurally complete; real inference call needs a GPU deployment)*

## Delivery Layer

- [API (apps/api)](../../apps/api/README.md) *(implemented, Phase 4-5 - full project lifecycle over HTTP, auth, plan/storyboard/render-plan retrieval, retry-generation, asset upload)*
- [Frontend (apps/web-dashboard)](../../apps/web-dashboard/README.md) *(implemented, Phase 5 - Next.js dashboard + creative workspace)*
- [Post-Processing](../../services/post-processing/README.md) *(implemented, Phase 6 - Timeline Builder, Transition Engine, Audio Pipeline, Subtitle System, Thumbnail Engine, Watermark Engine, FfmpegCompositor; real ffmpeg execution)*
- [Export Service](../../services/export-service/README.md) *(implemented, Phase 6 - format/quality-preset export, Asset Packaging/RenderManifest)*

## Cross-cutting

- [Asset Manager](../../services/asset-manager/README.md)
- [Config SDK](../../packages/config-sdk/README.md)
- [Observability](../../packages/observability/README.md)
- [Director Memory](../../packages/director-memory/README.md)
- [Project Persistence](../../packages/persistence/README.md) *(implemented, Phase 4)*
- [Auth](../../packages/auth/README.md) *(implemented, Phase 5 - provider-independent, personal workspace per user)*

## Contracts

- [Schemas](../../packages/schemas/README.md)
- [LLM Providers](../../packages/llm-providers/README.md)
- [Prompt Engine](../../packages/prompt-engine/README.md)
- [Video Engine SDK](../../packages/video-engine-sdk/README.md)
- [Video Composition SDK](../../packages/video-composition-sdk/README.md) *(implemented, Phase 6 - IRenderCompositor/ITransitionPlugin/IUpscaler)*
- [Storage SDK](../../packages/storage-sdk/README.md)

## Content

- [Prompt Library (video-gen fragments)](../../libraries/prompt-library/README.md)
- [Prompt Templates (LLM director prompts)](../../libraries/prompt-templates/README.md)
- [Template Library (DirectorPlan genre templates)](../../libraries/template-library/README.md)

## Future

- [Training](../../services/training/README.md)
