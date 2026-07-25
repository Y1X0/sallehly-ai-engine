# packages/cinematic-intelligence-sdk

Engine-agnostic contracts for the Cinematic Intelligence Layer (Phase 7)
- the subsystem that sits between the Creative Compiler and the Video
Engine Adapter and is responsible for one thing: making a project's
independently-generated shots read as one film. It never generates
pixels and it never talks to a specific engine (Wan2.1, Veo, Runway,
Luma, Kling, Pika, ...) - it only produces/consumes the types below,
same boundary discipline as ADR 0001.

| Interface | Role | Registry / concrete implementation |
|---|---|---|
| `IGraphStore` | Storage abstraction for the Director Memory Graph | `InMemoryGraphStore` (`services/cinematic-intelligence`) - prepared for Neo4j or similar later |
| `IRepairStrategy` | One repair type (`prompt_repair`/`camera_repair`/`style_repair`/`identity_repair`/`lighting_repair`) for the Automatic Repair Engine | `config_sdk.registry.REPAIR_STRATEGY_REGISTRY`, built-ins in `services/cinematic-intelligence/repair/` |
| `IPromptTranslator` | Translates an engine-agnostic `PromptPackage` into one engine's preferred phrasing | `config_sdk.registry.PROMPT_TRANSLATOR_REGISTRY`, built-ins in `services/cinematic-intelligence/prompt_intelligence/translators.py` |
| `IQualityMetric` | One scoring dimension for the Scene Quality Analyzer | `config_sdk.registry.QUALITY_METRIC_REGISTRY`, built-ins in `services/cinematic-intelligence/quality_analyzer.py` |
| `IEmbeddingProvider` | Prepared interface for a future CLIP/DINO-backed perceptual scorer | **not implemented** - see below |
| `IReferenceConditioningAdapter` | Prepared interface for a future ControlNet/IP-Adapter conditioning path | **not implemented** - see below |

## Types

`types.py` mirrors the corresponding JSON Schemas exactly (same
dict-in-the-pipeline / dataclass-at-the-boundary pattern as
`video_engine_sdk.types`/`video_composition_sdk.types` - see ADR 0009):

| Dataclass | Schema |
|---|---|
| `CharacterIdentityProfile`, `CharacterAttributes`, `HairProfile`, `ExpressionEntry`, `LoraBinding` | `character_identity_profile.schema.json` |
| `ObjectProfile`, `ObjectAttributes`, `ObjectLocationEntry` | `object_profile.schema.json` |
| `EnvironmentProfile` | `environment_profile.schema.json` |
| `ContinuityReport`, `ContinuityViolation` | `continuity_report.schema.json` |
| `StyleLock`, `GrainSetting`, `BloomSetting` | `style_lock.schema.json` |
| `ReferencePackage`, `ReferenceImageEntry`, `ConditioningReadiness` | `reference_package.schema.json` |
| `PromptPackage`, `PromptSourceContext`, `PromptScore` | `prompt_package.schema.json` |
| `ProjectMemory`, `MemoryEvent`, `CameraMemoryState`, `TimelineEntry` | `project_memory.schema.json` |
| `QualityReport`, `QualityScores`, `QualityIssue` | `quality_report.schema.json` |
| `RepairAction` | `repair_action.schema.json` |
| `GraphNode` | `graph_node.schema.json` |
| `GraphEdge` | `graph_edge.schema.json` |

## Why two interfaces are prepared, not implemented

`IEmbeddingProvider` (CLIP/DINO perceptual embeddings) and
`IReferenceConditioningAdapter` (ControlNet/IP-Adapter generation-time
conditioning) both need a deployed vision/generation model this sandbox
does not have - the same class of limitation as real GPU inference in
`workers/gpu-worker`. Every Phase 7 consistency/continuity/quality score
is instead computed from structured metadata (profiles, continuity
reports, style locks, project memory) that this codebase can actually
produce and test. See `docs/adr/0013-cinematic-intelligence-layer.md`.

## Why a separate package from video-composition-sdk / video-engine-sdk

Post-production compositing, generation, and cinematic intelligence are
three independent axes of change. A continuity-rule change never
touches, or even imports, anything ffmpeg- or engine-related, and
`CreativeCompiler`/`GenerationPipeline`/`services/post-processing` stay
entirely unaware this package exists.
