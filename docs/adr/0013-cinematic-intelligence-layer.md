# ADR 0013: The Cinematic Intelligence Layer - deterministic consistency, not a vision model

**Status:** Accepted

## Context

Phase 7 asks for a "Cinematic Intelligence Layer" sitting between the
Creative Compiler and the Video Engine Adapter, whose job is "not to
generate video" but to "guarantee cinematic consistency across the
entire project regardless of the underlying model" - character/object/
environment consistency, scene/camera continuity, a style lock, a
reference image engine, prompt intelligence, temporal memory, a
director memory graph, a quality analyzer, and an automatic repair
engine, all "engine agnostic, provider agnostic, plugin architecture."
It explicitly forbids training any model.

This is a different kind of boundary than any earlier phase. Phase 6
found that `ffmpeg` was a real, installable dependency and held itself
to a correspondingly higher execution bar. Phase 7's honest ceiling is
lower on one specific axis: judging whether two shots *actually look*
consistent (same face, same lighting, same camera geometry) is a
computer-vision problem - it needs a deployed embedding model (CLIP/
DINO) or a generation-time conditioning model (ControlNet/IP-Adapter),
neither of which exists in this sandbox, and Phase 7 explicitly
forbids training one. So this layer's real, tested contribution is
everything that *can* be decided from structured metadata alone:
immutable identity/object/environment records, rule-based continuity
checks between adjacent shots' camera/blocking/timing data, a locked
global style, and prompts built from that memory instead of raw text -
while the two genuinely vision-dependent interfaces are prepared and
explicitly not implemented, the same honesty standard `PassthroughUpscaler`
(ADR 0012) and the unexecuted GPU/Temporal boundaries were held to.

## Decisions

### 1. Two new packages, the same generation/post-production pattern

`packages/cinematic-intelligence-sdk` (dataclasses mirroring every new
schema, plus `IRepairStrategy`/`IPromptTranslator`/`IQualityMetric`/
`IGraphStore`/`IEmbeddingProvider`/`IReferenceConditioningAdapter`) is
a third independent-axis contract package alongside `video-engine-sdk`
(generation) and `video-composition-sdk` (post-production) - a
continuity-rule change never touches, or even imports, ffmpeg- or
engine-related code. `services/cinematic-intelligence` holds every
concrete engine. Three new `config_sdk.Registry` instances
(`PROMPT_TRANSLATOR_REGISTRY`, `QUALITY_METRIC_REGISTRY`,
`REPAIR_STRATEGY_REGISTRY`) reuse the exact mechanism
`TRANSITION_PLUGIN_REGISTRY` established in ADR 0012 - register a
class, look it up by key, no engine ever branches on which one is
active.

### 2. Identity is immutable; state is not

`CharacterIdentityProfile` and `StyleLock` are created once
(`locked: true`, schema-enforced as a `const`) and never mutated in
place - "generate immutable Character Identity Profiles... never
regenerate identity, only reuse" is the literal requirement.
`ObjectProfile` and `EnvironmentProfile` are the opposite: an object's
*name/materials* are fixed at establishment, but its `location_history`/
`damage_state` (object) and `weather`/`time_of_day` (environment, via
`update()`) are expected to evolve across a story. The distinction
matters for `EnvironmentConsistencyEngine.detect_drift()`: a
*deliberate* change goes through `update()`; anything that shows up
unannounced in a later shot is exactly the "impossible jump" this layer
exists to catch.

### 3. Continuity checking is a metadata diff, not a vision model

`SceneContinuityEngine`/`CameraContinuityEngine` compare two adjacent
shots' plain-dict continuity state (entry/exit points, eye lines,
actor positions, motion direction, timing; lens/height/movement/
framing) using fixed compatibility tables (the 180-degree rule's
screen-left/screen-right pairing, opposite-movement pairs, coarse
angle/shot-type rank distances) and emit `ContinuityReport` violations
with a severity. This is deliberately legible and testable - every
violation type has a concrete, deterministic trigger condition, unlike
a similarity score from an embedding model would be. `StyleLockEngine.
check_drift()` and `EnvironmentConsistencyEngine.detect_drift()` follow
the same pattern for style and environment.

### 4. `SceneQualityAnalyzer` scores are rule-based, and say so on the wire

`QualityReport.embeddings_used` is a schema-level `const: false` - not
just a docstring claim but a field a caller can check. Every built-in
`IQualityMetric` derives its score from `ContinuityReport`/`StyleLock`/
`PromptPackage.score` violations already computed elsewhere in this
layer, via a fixed severity-to-penalty table (critical -0.4, warning
-0.15, info -0.05), not from inspecting rendered pixels. `IEmbeddingProvider`
(CLIP/DINO) is prepared as an interface a future metric could use, but
no concrete implementation ships - the same "prepared, not implemented"
posture as `IUpscaler` (ADR 0012) and real GPU inference
(`workers/gpu-worker`), for the same reason: it needs a deployed model
this sandbox doesn't have, and Phase 7 explicitly forbids training one.

### 5. The Automatic Repair Engine proposes concrete fixes, scoped to one shot

`AutomaticRepairEngine` routes a `QualityReport`'s single worst-scoring
dimension to the matching `IRepairStrategy` (identity/camera/style/
lighting/prompt) - never more than one repair_type per call, and the
resulting `RepairAction.shot_id` is always the report's own shot_id, by
construction. Strategies that have nothing to act on (no last-known-good
camera, no character profile, ...) return `status="failed"` rather than
fabricating a fix - a real, tested failure path, not just a happy path.

### 6. `IGraphStore`: in-memory now, Neo4j-shaped later

`DirectorMemoryGraph` is a thin facade over `IGraphStore`
(`add_node`/`add_edge`/`get_node`/`nodes_by_type`/`neighbors`) with
deterministic node ids (`node_<type>_<ref_id>`) so re-recording the
same subject is idempotent. `InMemoryGraphStore` is the only concrete
implementation - sufficient for single-process testing and for a future
AI Director to query today; a real graph database swaps in behind the
same interface without `DirectorMemoryGraph` or any caller changing,
the same swap-point discipline as `IProjectStore` (`packages/persistence`).

### 7. Reference conditioning is prepared, not implemented

`ReferenceImageEngine` builds real `ReferencePackage`s (bundles of
asset ids with roles), but `prepared_for.controlnet`/`ip_adapter`
default to `false` and no generation-time conditioning actually runs -
`IReferenceConditioningAdapter` documents where it would plug in later,
without `RenderSpec` (`render_configuration.schema.json`) or any
`IVideoEngine` implementation changing shape today. Same reasoning as
Decision 4: it needs an engine/adapter combination this codebase
doesn't have.

## Consequences

- `docs/DEV_SETUP.md` needs no new prerequisite - everything in this
  layer is pure Python, no external binary or model download, unlike
  Phase 6's `ffmpeg` requirement.
- Coverage on every new module is ≥95% (`pytest-cov`, added as a dev
  dependency this phase); the handful of uncovered lines are all the
  same class of defensive `schemas.validate(...)` exception branch that
  cannot be reached without an internal bug, never a reachable code
  path through the public API.
- This layer is not yet wired into `ProjectLifecycle`/`apps/api`/
  `apps/web-dashboard` - same posture Phase 6 shipped with (ADR 0012's
  Consequences). The natural integration point is between the Render
  Configuration Compiler and `GenerationPipeline`: a `PromptPackage`
  built from resolved `CharacterIdentityProfile`/`ObjectProfile`/
  `EnvironmentProfile`/`StyleLock` state would fill a `RenderSpec`'s
  `positive_prompt`/`negative_prompt` before `IVideoEngine.build_job_payload`
  is ever called, with `SceneQualityAnalyzer`/`AutomaticRepairEngine`
  running after each `GenerationJob` completes - wiring that is the
  natural next phase, not attempted here per the same "build and test
  the layer, integrate later" pattern as Phase 6.
- `IEmbeddingProvider` and `IReferenceConditioningAdapter` remaining
  unimplemented means every consistency/quality signal in this phase is
  ultimately only as good as the metadata callers supply (continuity
  state dicts, resolved profiles) - it cannot catch a drift that never
  shows up in that metadata. This is the honest ceiling of a
  metadata-only system and is not a limitation future phases can close
  without a real vision model deployment.
