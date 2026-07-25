# ADR 0014: Pipeline integration - wiring Phase 6/7 into the live project flow

**Status:** Accepted

## Context

Phases 6 (Post-Processing & Export) and 7 (Cinematic Intelligence Layer)
both shipped as real, tested, standalone modules that `ProjectLifecycle`
never called - each phase's own ADR (0012, 0013) says so explicitly in
its Consequences section, and the roadmap in `docs/ARCHITECTURE.md`
already named "wiring post-production + cinematic intelligence into
`ProjectLifecycle`/API/frontend" as Phase 8 - Scale-out's first bullet.
This phase does exactly that integration, plus two things it enables:
real API endpoints/dashboard for the newly-wired Cinematic Intelligence
Layer, and closing a gap this work surfaced - `apps/api` never actually
read the video-engine config switch it already had. Training a custom
model (Phase 9) is explicitly out of scope, same boundary Phase 7 held.

## Decisions

### 1. `CinematicIntelligenceCoordinator` is the one integration point for all ten Phase 7 engines

`services/cinematic-intelligence/coordinator.py` is new: it instantiates
Character/Object/Environment Consistency, Scene/Camera Continuity, Style
Lock, Prompt Intelligence, Temporal Memory (+ Director Memory Graph),
Scene Quality Analyzer, and Automatic Repair as its own attributes and
exposes exactly the operations the rest of the system needs -
`enrich_render_plan`, `get_project_report`, `improve_prompt`,
`repair_shot`, `review_repair`, `list_repairs` - against real
`DirectorPlan`/`RenderPlan` dicts, not the synthetic fixtures Phase 7's
own tests used. Nothing outside this module reaches into an individual
engine directly; a future caller (a second orchestrator, a CLI) gets the
same guarantees `ProjectLifecycle` does through the same six methods.

Two honest limitations came directly from `DirectorPlan`'s actual shape,
not from the coordinator cutting corners:

- `Scene.characters` is a list of plain name strings (no face/hair/
  clothing/age/skin-tone brief), so `CharacterAttributes` placeholders
  are built from the name alone. The *consistency* guarantee is still
  real - the same character always gets the same profile, reused across
  every shot - only the profile's *richness* is limited by what the
  Creative Compiler currently produces upstream.
- `DirectorPlan`/`Shot` has no object-reference field at all, so
  `ObjectConsistencyEngine` is reachable through the coordinator and the
  new API routes but never auto-populated from scene data - objects must
  be established manually, the same "wired, not auto-detected from free
  text" posture Phase 7's own tests already used for this engine.

### 2. Enrichment runs at plan-compile time, not after generation

`ProjectLifecycle._enrich_render_plan` calls
`CinematicIntelligenceCoordinator.enrich_render_plan` immediately after
`CreativeCompiler.compile_render_plan`, inside both `approve_storyboard`
and `reject_render_plan`'s regeneration path - so every `RenderSpec` a
human reviews at gate 2 already carries CIL-built prompts and any
continuity violations are already on record, before any GPU cost is
spent. This differs from what ADR 0013's Consequences section
speculated (analysis "after each `GenerationJob` completes"); running it
pre-generation instead means `QualityReport`/`RepairAction` are honestly
scored against *planned* continuity/style/camera metadata, never against
rendered pixels - consistent with ADR 0013's `embeddings_used: false`
guarantee, just earlier in the flow than first assumed. No extra
storage call is needed: `render_plan["render_specs"]` list items are the
same dict objects already held by `IDirectorMemoryStore`, so mutating a
spec's `positive_prompt`/`negative_prompt` in place is visible to every
later reader without re-recording anything.

`cinematic_intelligence`/`post_production` are optional constructor
parameters on `ProjectLifecycle`, defaulting to `None` - every Phase
4-7 caller and test that builds a `ProjectLifecycle` without them keeps
working exactly as before; only `apps/api/state.py` and any test that
opts in via `tests/conftest.py`'s new `with_cinematic_intelligence`/
`with_post_production` flags exercises the wiring.

### 3. `finalize_project` is a new, explicit, separately-triggered step past `COMPLETED`

`ProjectStatus` gains `POST_PROCESSING`/`EXPORTED`, added strictly after
`COMPLETED` rather than replacing what it means - `COMPLETED` still
means exactly what it meant in Phases 4-7 ("every shot generated"), and
`generate_video`/`retry_generation` never call `finalize_project`
automatically. `PostProductionRunner` (new, `services/render-orchestrator`)
bridges `GenerationPipeline`'s per-shot `AssetManager` records into the
Phase 6 pipeline unchanged - `TimelineBuilder` -> `FfmpegCompositor` ->
`ExportService` -> `AssetPackager` - reusing every Phase 6 module as-is.

On failure, `finalize_project` reverts the project to `COMPLETED` (not
`FAILED`) and records `error_message`, so a failed export can be safely
retried without colliding with `FAILED`'s existing meaning ("generation
failed", which `retry_generation` depends on). This was verified against
a real failure mode, not a hypothetical one: `LocalProvider` (the
offline Phase 3 compute stub) writes placeholder JSON as its "video"
output rather than real bytes, so `ffmpeg` correctly rejects it -
`finalize_project` surfaces this as a clean `ProjectLifecycleError`
(409 over HTTP), never a crash, and the same code path was independently
verified to succeed end-to-end (real exported video + manifest) once
given real ffmpeg-generated clips - proof the post-production wiring
itself is correct, and that the failure is `LocalProvider`'s honest
limitation, not a Phase 8 bug.

### 4. New API surface: `/projects/{id}/cinematic/*` and `/finalize` + `/render-manifest`

`apps/api/src/api/routes/cinematic.py` (new) exposes `analyze`/`report`
(live `get_project_report`), `prompts/{shot_id}/improve`,
`repair/{shot_id}`, `repairs` (list), and `repairs/{id}/approve|reject` -
every route resolves `CinematicIntelligenceCoordinatorError` (unknown
project/shot/repair) to 404, follows the same ownership-check pattern
(`_get_owned_project`, 403 for a non-owner) every existing project route
already uses. `routes/projects.py` gains `POST /{id}/finalize` (409 if
not `COMPLETED` or no `PostProductionRunner` configured) and
`GET /{id}/render-manifest` (404 until finalized).

### 5. Model adapters: real where a technique doesn't need a GPU, `ModelUnavailableError` where it does

`services/cinematic-intelligence/model_adapters/` implements
`IEmbeddingProvider` (`ClipEmbeddingProvider`, `DinoEmbeddingProvider`)
and `IReferenceConditioningAdapter` (`ControlNetConditioningAdapter`,
`IPAdapterConditioningAdapter`) - the two interfaces ADR 0013 left
prepared-not-implemented. Every method needing a real deployed model
lazily imports its dependency (`open_clip`/`torch`/`torchvision`/
`controlnet_aux`/`transformers` - none installed in this sandbox,
confirmed) and raises `ModelUnavailableError` with an actionable
install/deploy message, never a bare `ImportError` and never a
fabricated result; registering an adapter costs nothing regardless of
what's installed, since no heavy import happens at class-definition
time.

One path clears a higher bar deliberately:
`ControlNetConditioningAdapter`'s default `preprocessor="canny"` mode
runs genuine Pillow `ImageFilter.FIND_EDGES` edge detection against a
real image resolved through an injected `AssetManager` - classical image
processing, not a trained model, so it is fully functional in this
sandbox with no GPU. This was a deliberate correction mid-phase: an
earlier draft had both conditioning adapters as a trivial
"append `asset_id` to `conditioning_images`" passthrough, which did not
clear the bar `IReferenceConditioningAdapter`'s own docstring set
("beyond the existing plain `conditioning_images` passthrough"). Cosine
similarity (`IEmbeddingProvider.similarity`) is likewise pure Python and
always real, independent of which (if any) embedding backend produced
the vectors being compared. `config_sdk` gains
`EMBEDDING_PROVIDER_REGISTRY`/`CONDITIONING_ADAPTER_REGISTRY`, the same
`Registry` pattern as every other swap point.

### 6. `VIDEO_ENGINE_REGISTRY`/`Settings.video_engine` were dead code; now they aren't

`apps/api/src/api/state.py` had imported `Wan21Adapter` and constructed
it directly since Phase 4, never actually reading
`VIDEO_ENGINE_REGISTRY`/`settings.video_engine` despite both already
existing (`packages/config-sdk`, ADR 0009) - a real gap, not a
hypothetical one, found while implementing task 6's "switch between
Wan2.1/future Sallehly Model/other video engines without changing the
core pipeline" requirement. Fixed: `build_app_state` now calls
`VIDEO_ENGINE_REGISTRY.create(settings.video_engine)`.
`SallehlyModelAdapter` (`services/video-engine-adapter`) is a second
real `IVideoEngine` registered as `sallehly-v1`, proving the swap:
`capabilities()` is real declarative metadata for the eventual Phase 9
foundation model, while `build_job_payload`/`parse_result` correctly
raise `SallehlyModelNotTrainedError` (no weights exist yet) rather than
fabricating a container image or a fake `RawClip` - the same "prepared,
not implemented" class of honesty as Wan2.1 inference without a
deployed GPU. `GenerationPipeline`/`RenderConfigCompiler`/
`ProjectLifecycle` needed zero code changes to support the swap -
verified by driving a project through the full lifecycle with
`Settings(video_engine="sallehly-v1")` and observing it fail exactly at
`build_job_payload`, with every step before that identical to the
`wan2.1` path.

### 7. Dashboard: a read-mostly Cinematic Intelligence panel

`CinematicIntelligencePanel.tsx` (new) renders overall + five dimension
scores, detected problems, and repair suggestions/proposed repairs with
approve/reject actions - populated automatically once a project reaches
any post-storyboard-approval status (`ProjectWorkspace.tsx`'s
`CINEMATIC_ANALYSIS_STATUSES`), since enrichment already ran during
`approve_storyboard`. The panel itself triggers no analysis - it is a
view over `CinematicIntelligenceCoordinator.get_project_report`, plus
the repair action buttons, following the existing `fetchOptional`
404-tolerant fetch pattern already used for plan/storyboard/render-plan.

## Consequences

- Every Phase 4-7 test and every pre-existing caller of `ProjectLifecycle`
  is unaffected - `cinematic_intelligence`/`post_production` are opt-in
  via constructor kwargs, and `tests/conftest.py`'s `build_stack()`
  defaults both to off.
- `finalize_project` genuinely fails against the default `LocalProvider`
  stack (placeholder JSON, not real video bytes) - this is
  `LocalProvider`'s pre-existing, unrelated limitation from Phase 3, not
  new to this phase; a real `IComputeProvider`/`IVideoEngine` pair
  producing real video files hits no such failure, verified directly.
- `IEmbeddingProvider`/`IReferenceConditioningAdapter` still cannot
  produce a real embedding or a real ControlNet/IP-Adapter conditioning
  pass in this sandbox - `ModelUnavailableError` is the correct, tested
  outcome for every method that needs `torch`/`open_clip`/
  `torchvision`/`controlnet_aux`/`transformers`, none of which are
  installed here. Only the canny preprocessing path is genuinely
  exercised end-to-end.
- `ObjectConsistencyEngine` remains unreachable from real scene data
  automatically - `DirectorPlan` would need a new object-reference field
  (Creative Compiler / Scene Generator change) before this closes; it is
  not a Phase 8 regression, the same gap ADR 0013 already documented.
- `SallehlyModelAdapter` has no trained weights - `services/training`
  (Phase 9) is unstarted, unchanged from ADR 0013's boundary. The
  adapter's value this phase is proving the swap point is real, not
  producing video.
- `docs/DEV_SETUP.md` needs no new required prerequisite: every new
  module here is pure Python plus (optionally) the same `ffmpeg` Phase 6
  already required for `finalize_project`; `torch`/`open_clip`/etc. are
  documented as optional installs for whoever deploys real model
  adapters later, never required to run the test suite or the API.
