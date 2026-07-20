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

## Execution Layer

- [Video Engine Adapter](../../services/video-engine-adapter/README.md)
- [Render Orchestrator](../../services/render-orchestrator/README.md)
- [GPU Worker](../../workers/gpu-worker/README.md)

## Delivery Layer

- [Post-Processing](../../services/post-processing/README.md)
- [Export Service](../../services/export-service/README.md)

## Cross-cutting

- [Asset Manager](../../services/asset-manager/README.md)
- [Config SDK](../../packages/config-sdk/README.md)
- [Observability](../../packages/observability/README.md)
- [Director Memory](../../packages/director-memory/README.md)

## Contracts

- [Schemas](../../packages/schemas/README.md)
- [LLM Providers](../../packages/llm-providers/README.md)
- [Prompt Engine](../../packages/prompt-engine/README.md)
- [Video Engine SDK](../../packages/video-engine-sdk/README.md)

## Content

- [Prompt Library (video-gen fragments)](../../libraries/prompt-library/README.md)
- [Prompt Templates (LLM director prompts)](../../libraries/prompt-templates/README.md)
- [Template Library (DirectorPlan genre templates)](../../libraries/template-library/README.md)

## Future

- [Training](../../services/training/README.md)
