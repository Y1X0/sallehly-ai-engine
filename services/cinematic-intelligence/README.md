# services/cinematic-intelligence

## Cinematic Intelligence Layer (Phase 7)

**Responsibility:** Sits between the Creative Compiler and the Video
Engine Adapter. It never generates pixels - its job is to guarantee
that a project's independently-generated shots read as one film
regardless of which engine (Wan2.1, Veo, Runway, Luma, Kling, Pika, a
future Sallehly model, ...) rendered them, by maintaining persistent
identity/continuity/style memory and building every shot's prompt from
that memory instead of a raw, isolated description.

**Input:** A project's DirectorPlan/Storyboard/RenderPlan (Phases 1-2)
plus, as generation proceeds, each shot's resolved camera/lighting/
style and its generated RawClip (Phase 3).

**Output:** CharacterIdentityProfile/ObjectProfile/EnvironmentProfile
records, ContinuityReports, a project StyleLock, ReferencePackages,
PromptPackages (consumed by the Render Configuration Compiler to fill a
RenderSpec's `positive_prompt`/`negative_prompt`), a ProjectMemory, a
Director Memory Graph, QualityReports, and RepairActions.

**Consumed by:** Render Configuration Compiler (PromptPackage), a
future ProjectLifecycle integration (everything else) - see "Status"
below for why that wiring isn't done yet.

## Modules

| Module | Responsibility |
|---|---|
| `CharacterConsistencyEngine` | Creates immutable CharacterIdentityProfiles once, reused (never regenerated) by every shot referencing that character_id |
| `ObjectConsistencyEngine` | Tracks persistent objects' materials/colors/damage state and location history |
| `EnvironmentConsistencyEngine` | Tracks a location's weather/time-of-day/season/architecture/layout; `detect_drift()` catches an accidental "impossible jump" before it's recorded |
| `SceneContinuityEngine` | Compares two adjacent shots' entry/exit points, eye lines, actor positions, motion direction, and timing -> a `ContinuityReport` (`scope='scene'`) |
| `CameraContinuityEngine` | Compares two adjacent shots' lens/height/movement/framing -> a `ContinuityReport` (`scope='camera'`) |
| `StyleLockEngine` | Locks one global `StyleLock` per project (grading/film-stock/grain/DOF/bloom/lens effects); `check_drift()` flags a shot's style_override diverging from it |
| `ReferenceImageEngine` | Builds reusable `ReferencePackage`s (character/object/environment/style/pose reference images) |
| `prompt_intelligence/` (`PromptIntelligenceEngine`) | `PromptOptimizer` + `NegativePromptBuilder` + `PromptCompressor` + `PromptScorer` + `PromptVersioning`, plus `IPromptTranslator` plugins (`PROMPT_TRANSLATOR_REGISTRY`) for wan2.1/veo/runway/luma/kling/pika |
| `TemporalMemoryEngine` | Maintains one `ProjectMemory` per project, updated after every generated shot |
| `DirectorMemoryGraph` + `InMemoryGraphStore` | The graph memory backbone (`IGraphStore`) - character/object/location/event/style nodes, appears_in/uses/wears/located_at/moves_to/speaks_to edges |
| `SceneQualityAnalyzer` | Scores a shot's identity/camera/lighting/style/composition/prompt/motion quality from continuity + prompt signals via `IQualityMetric` plugins (`QUALITY_METRIC_REGISTRY`) |
| `AutomaticRepairEngine` | Routes a `QualityReport`'s worst-scoring dimension to the matching `IRepairStrategy` (`REPAIR_STRATEGY_REGISTRY`) - always scoped to one shot |

## Plugin architecture

Every extension point is a `config_sdk.Registry`, the same mechanism
`TRANSITION_PLUGIN_REGISTRY` uses (ADR 0012): `PROMPT_TRANSLATOR_REGISTRY`,
`QUALITY_METRIC_REGISTRY`, `REPAIR_STRATEGY_REGISTRY`. A custom plugin
implements the matching interface from `cinematic-intelligence-sdk`
(`IPromptTranslator`/`IQualityMetric`/`IRepairStrategy`) and registers
under its own key - no engine ever branches on which one is active.
Call `cinematic_intelligence.register_defaults()` once at process
startup (or freely again in tests) to register every built-in.

## Status (Phase 7, wired Phase 8)

Implemented and tested with real deterministic logic throughout - no
LLM, no vision model, no trained classifier anywhere in the ten
consistency/continuity/quality engines. `IGraphStore`'s only concrete
implementation is in-memory; Neo4j or similar is a later swap.

`CinematicIntelligenceCoordinator` (`coordinator.py`) is the single
integration point wiring all ten engines together against real
`DirectorPlan`/`RenderPlan` data, and is what `ProjectLifecycle`/
`apps/api` actually call - see `docs/adr/0014-pipeline-integration.md`.
`model_adapters/` now gives `IEmbeddingProvider`/
`IReferenceConditioningAdapter` concrete implementations: real where a
technique needs no trained model (cosine similarity,
`ControlNetConditioningAdapter`'s default Canny edge detection via
Pillow), and a clear `ModelUnavailableError` everywhere a real deployed
model (`torch`/`open_clip`/`torchvision`/`controlnet_aux`/
`transformers`) is genuinely required and not installed here - see
`packages/cinematic-intelligence-sdk/README.md`.
