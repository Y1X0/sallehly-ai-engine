# ADR 0021: Phase 9 Preparation - training framework, dataset pipeline, model registry, evaluation framework, training configs

**Status:** Accepted

## Context

The Phase 8 readiness audit (see the Phase 9 Readiness Audit report
delivered alongside this ADR) confirmed the platform's abstraction
layers (`IVideoEngine`, `IComputeProvider`, `GenerationPipeline`,
`ProjectLifecycle`, `CinematicIntelligenceCoordinator`, Post-Processing,
Export Pipeline) are architecturally ready to receive a custom Sallehly
video model, and that every remaining blocker is ML content - weights,
a dataset, a training pipeline, an evaluation harness, a model registry
- none of which existed. Per explicit instruction, this phase builds
everything required *before* the first GPU training run, without
training a model, downloading a model, or requiring a GPU anywhere.
`services/training` had been a README-only placeholder since Phase 0
(explicitly excluded from the uv workspace, `pyproject.toml`'s
`[tool.uv.workspace] exclude`) - this ADR is what turns it into a real
package.

## Decisions

### 1. `services/training`: five real, CPU-only submodules, one flat `__init__.py` surface

`config.py` (`TrainingConfig`/`LoRAConfig`/`BASE_MODEL_REGISTRY`),
`trainer.py` (`ITrainer`/`DryRunTrainer`), `checkpoint.py`
(`ICheckpointStore`/`InMemoryCheckpointStore`/`FilesystemCheckpointStore`),
`dataset/` (ingest -> caption -> validate -> dedup -> split -> statistics
-> version), `registry/` (`IModelRegistry`/`FilesystemModelRegistry`,
promotion/rollback/compatibility), `evaluation/` (metrics, benchmark
runner, human eval, quality reports, regression detection). Every
module follows the same interface-plus-real-default-implementation
shape as every other cross-cutting concern in this codebase
(`IProjectStore`, `ICache`, `IRateLimiter`, ...) - flattened into
`training/__init__.py` the same way `cinematic_intelligence/__init__.py`
re-exports every submodule's public surface at the top level.

### 2. Real work is CPU-only; model-needing work raises `ModelUnavailableError`, not a silent no-op

Dataset metadata extraction (`extract_clip_metadata`) runs a genuine
`ffprobe` subprocess and computes a real SHA-256 file hash - both
already-installed system tools, no new dependency. `HeuristicCaptionProvider`
and `HashDuplicateDetector` are real, deterministic, always-available
defaults. Where a real implementation genuinely needs a trained model
this environment doesn't have - `VLMCaptionProvider` (dense captioning),
`EmbeddingDuplicateDetector` (near-duplicate detection via perceptual
embeddings), `FVDMetric`/`CLIPScoreMetric` (video-quality scoring) -
each raises a local `training.errors.ModelUnavailableError` with a
message naming exactly what's missing, the same honesty pattern
`cinematic_intelligence.model_adapters.errors.ModelUnavailableError`
already established (Phase 7/8). `training`'s own `ModelUnavailableError`
is a separate class, not imported from `cinematic_intelligence`,
keeping the two services decoupled even though they share the same
gap-marking idiom.

### 3. `DryRunTrainer`: proves the training orchestration loop without touching a GPU

`ITrainer.train(config) -> TrainingRunResult` is deliberately as small
as `IVideoEngine`/`IComputeProvider` (one method) - a future real
trainer (calling into `accelerate`/`diffusers` on real GPU hardware)
implements the same interface, changing nothing above it. `DryRunTrainer`
genuinely executes a step loop, an `on_step` callback hook (where Stage
7's eval-cadence integration attaches), and periodic checkpointing with
a synthetically decreasing loss value - real Python control flow, zero
GPU, zero dataset bytes read, the same "prove the pipeline shape before
the expensive resource exists" pattern `LocalProvider` already
established for compute jobs (`video_engine_adapter.compute.local_provider`,
ADR 0009).

### 4. Dataset pipeline: content-addressable clip identity and dataset versioning

`DatasetManager.ingest()` derives `clip_id` from the file's SHA-256 hash
(`clip_<hash[:16]>`), not a counter or filename - re-ingesting identical
bytes under a different name or path always resolves to the same
record, which is also why duplicate re-ingestion is a non-issue and
`HashDuplicateDetector`'s real job is finding *distinct files with
identical content*. `compute_version_id()` similarly derives a
dataset's version id from the sorted set of `clip_id:file_hash` pairs
it contains - a `TrainingConfig.dataset_version` string can therefore be
trusted to mean "exactly this data," not a manually incremented label
someone forgot to bump. `assign_split()` uses a stable hash of
`f"{seed}:{clip_id}"` rather than seeded `random.shuffle` specifically
so a golden benchmark/test split survives new clips being added to the
pool later without reshuffling which existing clips are held out - a
real correctness property benchmarking (Stage 8) depends on.

### 5. Model Registry: `PromotionStatus` state machine + compatibility gate reusing `video_engine_sdk.CapabilityManifest` directly

`STAGING -> CANARY -> PRODUCTION` (or `REJECTED` from either), with
`PRODUCTION -> ARCHIVED -> CANARY` as the only path back in - enforced
by `registry.records.assert_valid_transition`, the same "the state
machine itself refuses invalid moves" discipline `ProjectLifecycle`
already uses for `ProjectStatus`. `ModelVersionRecord.capability_manifest`
is a real `video_engine_sdk.CapabilityManifest` - the exact type
`IVideoEngine.capabilities()` returns - so `registry.compatibility.validate_capability_manifest()`
checks a candidate version's declared envelope (modes, resolutions,
fps, motion-strength range) against the real fields
`RenderConfigCompiler`/`GenerationPipeline` actually read, not a guess.
Promoting to `CANARY` or `PRODUCTION` runs this check and refuses on any
structural error - this specifically catches the class of mistake this
codebase already made once for real: ADR 0014's `SallehlyModelAdapter`
shipping a placeholder `CapabilityManifest` nobody had checked against
what `IVideoEngine` callers require. `rollback()` reverts `PRODUCTION`
directly to whichever version held it immediately before - a documented,
deliberate bypass of the normal promotion ladder (rollback's entire
point is an instant revert to something already proven, not a re-run of
staged promotion under incident pressure).

### 6. Evaluation: `BenchmarkRunner` reimplements the generation dance directly rather than depending on `services/render-orchestrator`

`BenchmarkRunner` drives a `BenchmarkCase`'s `RenderSpec` through
`IVideoEngine.build_job_payload -> IComputeProvider.submit/poll/fetch_output
-> IVideoEngine.parse_result` itself - the same four-call sequence
`GenerationPipeline._run_once` performs - rather than importing
`GenerationPipeline`, which would pull `services/render-orchestrator`'s
full transitive dependency closure (persistence, cache, cinematic
intelligence) into `services/training` just to run a benchmark.
Genuinely executable today with zero GPU using `Wan21Adapter` +
`LocalProvider` (this codebase's own fully-offline test default);
pointing it at the untrained `SallehlyModelAdapter` correctly records
`SallehlyModelNotTrainedError` as a per-case error rather than crashing
the whole run - proof the harness is ready for a real checkpoint the
moment Phase 9 produces one, not just in theory.

### 7. Four real training configs, with real, independently-verified license facts

`services/training/configs/{wan21,hunyuanvideo,cogvideox,stable_video_diffusion}_finetune.yaml`
are real `TrainingConfig.to_yaml()` output, each validated by
`TrainingConfig.validate()`. `BASE_MODEL_REGISTRY`'s license facts were
checked via web search on 2026-07-25, not asserted from training data
alone: Wan2.1 is Apache-2.0 (matches this project's own `Wan21Adapter`
`CapabilityManifest`); HunyuanVideo's Tencent Community License permits
commercial use but excludes the EU/UK/South Korea and caps at 100M MAU
without a separate Tencent license; CogVideoX is Apache-2.0 only for the
2B variant, with the higher-quality 5B variant under a separate custom
license requiring independent review; Stable Video Diffusion's Stability
AI Community License is free only under $1M annual revenue, with a
mandatory "Powered by Stability AI" attribution above that. Each
`BaseModelInfo.commercial_use_verified` flag reflects this honestly -
`False` for CogVideoX and Stable Video Diffusion, since their
commercial terms are conditional, not unambiguous like Wan2.1's.

## Consequences

- `tests/test_training_framework.py` (config/LoRA/checkpoint/trainer),
  `tests/test_training_dataset.py` (real ffprobe execution via
  synthetic clips, same convention as Phase 6's post-processing tests),
  `tests/test_training_registry.py`, `tests/test_training_evaluation.py`
  (including two real executions of `BenchmarkRunner` against
  `Wan21Adapter`/`LocalProvider` and against the untrained
  `SallehlyModelAdapter`), and `tests/test_training_configs.py` (the
  four shipped YAML configs) - 133 new tests, all genuinely executed,
  no GPU or trained model required for any of them. Full suite: 611
  passed, 30 skipped (pre-existing Redis-server-not-running and
  Temporal-dev-server-not-running skips in this session, unrelated to
  this ADR).
- `services/training` was removed from `pyproject.toml`'s
  `[tool.uv.workspace] exclude` list (it is no longer a docs-only
  placeholder) and `rate-limit-sdk`/`quota-sdk`-class dependency
  discipline was followed from the start: `pyproject.toml` declares
  `video-engine-sdk` and `pyyaml` explicitly, nothing pulled in
  implicitly via the shared workspace venv.
- This ADR makes no changes to `IVideoEngine`, `IComputeProvider`,
  `GenerationPipeline`'s public contract, `ProjectLifecycle`'s public
  contract, `CinematicIntelligenceCoordinator`, Post-Processing, or the
  Export Pipeline - `services/training` is additive and currently
  unwired into any of them; nothing in `apps/api` or
  `services/render-orchestrator` imports it yet, since no work package
  requested wiring a UI/API surface for it in this pass.
- Remaining before a real GPU training run (unchanged by this ADR,
  since none of it is buildable without a GPU/dataset/trained model):
  a real GPU-backed `ITrainer`, a real licensed dataset, real
  `VLMCaptionProvider`/`EmbeddingDuplicateDetector`/`FVDMetric`/
  `CLIPScoreMetric` implementations, and `workers/gpu-worker`'s actual
  inference code (shared with Wan2.1, not Sallehly-specific - see the
  Phase 9 Readiness Audit).
