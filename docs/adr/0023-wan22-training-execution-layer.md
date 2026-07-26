# ADR 0023: Wan2.2 Training Execution Layer - entrypoint, dataset adapter, LoRA config, checkpoint pairing, evaluation hooks, controller/dispatch integration

**Status:** Accepted

## Context

ADR 0022 (training automation layer) shipped `run_experiment.py --dispatch`
deliberately unable to dispatch anything real: no training entrypoint
script existed for a Kaggle kernel or Modal function to run. This ADR
closes that gap for Wan2.2 specifically - the foundation model selected
after the base-model comparison report and the Wan2.2 fine-tuning
blueprint. Per explicit instruction, this is the *execution layer*
(entrypoint, interfaces, dataset/config/checkpoint plumbing, dispatch
wiring), not execution itself: no GPU is used, no Wan2.2 weights are
downloaded, and no real training runs anywhere in this change.

## Decisions

### 1. `services/training/src/training/wan22/`: a seventh submodule, same flattening convention

`backend.py`, `lora_config.py`, `dataset_adapter.py`, `checkpoint_writer.py`,
`trainer.py`, `evaluation_hooks.py`, `command.py`, `dispatch.py` -
flattened into `wan22/__init__.py` and then into the top-level
`training/__init__.py`, identical to how `dataset/`, `registry/`,
`evaluation/`, and `automation/` were added in ADR 0021/0022.

### 2. `BASE_MODEL_REGISTRY` gains three real, Apache-2.0 Wan2.2 entries

`wan2.2-ti2v-5b` (unified, single network, the Stage A pipeline-validation
target), `wan2.2-t2v-a14b` and `wan2.2-i2v-a14b` (both a two-expert MoE
DiT, the Stage B production targets) - license and architecture facts
carried forward from this session's own base-model comparison report and
Wan2.2 fine-tuning blueprint, not re-derived. `services/training/configs/
wan22_finetune.yaml` targets `wan2.2-ti2v-5b`: the cheapest, lowest-risk
first real GPU experiment once a backend exists.

### 3. `Wan22LoRAConfig.experts` makes "both MoE experts must train together" a type, not a convention

`expected_experts(base_model_id)` returns exactly `{"unified"}` for
TI2V-5B or exactly `{"high_noise", "low_noise"}` for either A14B variant.
`Wan22LoRAConfig.validate()` rejects any other expert set. There is no
way to construct a valid config that fine-tunes only one A14B expert -
the fine-tuning blueprint's single most important risk finding is
enforced structurally, the same way `PromotionStatus`'s transition table
(ADR 0021) makes an invalid model-registry state transition a type
error instead of a runtime mistake waiting to happen.

### 4. `Wan22CheckpointWriter` extends `ICheckpointStore` rather than replacing it

Reuses `FilesystemCheckpointStore`/`InMemoryCheckpointStore` exactly as
built in Phase 9 Preparation - no new storage mechanism. Expert identity
is encoded into the checkpoint id (`ckpt_{run_id}_{step:06d}_{expert}`)
rather than a new schema field, since `CheckpointRecord.metrics` is
typed `dict[str, float]` and expert names aren't numeric.
`get_paired_checkpoints()` is a real integrity check `Wan22LoRATrainer`
calls after every checkpoint write, not just a documented expectation -
it raises `PairedCheckpointMissingError` if any configured expert's
checkpoint is missing for that step.

### 5. `Wan22LoRATrainer(ITrainer)` trains every configured expert on every step, never independently

Same step/checkpoint loop shape `DryRunTrainer` (ADR 0021) proved out,
specialized so the expert loop is inside the step loop, not beside it -
structurally impossible to advance one expert's training without the
other(s) for an A14B run. The one real execution boundary is
`IWan22TrainingBackend.train_step()`/`save_checkpoint()`; its only
implementation, `UnavailableWan22Backend`, raises `ModelUnavailableError`
on the very first call, always. `Wan22LoRATrainer.train()` catches that
(the same try/except contract `DryRunTrainer` already established) and
returns a normal `TrainingRunResult(status="failed", ...)` - proving the
orchestration is genuinely wired end-to-end (verified by running the
real entrypoint script against a real dataset manifest during
development - see the script's own module docstring) while making real
training structurally impossible without a real backend attached.

### 6. `Wan22DatasetAdapter` is pure metadata transformation - no new file I/O beyond writing a manifest

Converts the real `ClipRecord`s `training.dataset.DatasetManager`
already produces into `Wan22ManifestEntry` records (video_path, caption,
resolution, num_frames, fps) - the caption-format shape the Wan2.2
fine-tuning blueprint specified. Refuses (raises, doesn't skip) any clip
missing a caption or rights clearance, matching `DatasetValidator`'s
existing posture. Never reads video bytes itself - `extract_clip_metadata`
already did that, for real, when the clip was ingested.

### 7. `Wan22EvaluationHook` wires Stage 7's eval-cadence hook to a real `IBenchmarkRunner`

`DryRunTrainer`'s `on_step` docstring (ADR 0021) already anticipated
this; `Wan22LoRATrainer(on_checkpoint=hook)` is where it attaches. The
hook itself does not import or construct `video_engine_adapter` - callers
inject a real `IVideoEngine`/`IComputeProvider`, keeping
`services/training`'s dependency-light discipline intact. Verified for
real in this session's own tests against `Wan21Adapter`+`LocalProvider`
(success path) and the untrained `SallehlyModelAdapter` (graceful
per-case error, not a crash) - the same proof pattern `BenchmarkRunner`
itself used in ADR 0021.

### 8. `TrainingCommand` is the single source of truth for "what command runs training," shared by every launcher

`build_training_command_for_job(job: JobRecord)` bridges
`TrainingController`'s planning output to a `TrainingCommand`;
`dispatch_via_kaggle()`/`dispatch_via_modal()` (item 8) both consume the
same `TrainingCommand` rather than building CLI args independently, so a
fourth launcher later needs one new `to_*()` method, not new
argument-building logic in three places. Both dispatch functions call
the real, already-tested `KaggleClient.push_kernel()`/
`ModalJobLauncher.launch()` from ADR 0022 - no new Kaggle/Modal
integration code, only wiring.

### 9. `run_experiment.py --dispatch` remains untouched in this change - dispatch is proven via direct unit tests instead

`dispatch_via_kaggle`/`dispatch_via_modal` are exercised directly in
`tests/test_training_wan22.py` with injected fake CLI runners (same
pattern as ADR 0022's own tests), proving the wiring is correct without
`run_experiment.py` itself gaining a code path that could attempt a real
`kaggle`/`modal` CLI invocation in an environment where neither is
configured. Wiring `--dispatch` through to these functions is
straightforward follow-up work, deliberately deferred rather than done
speculatively in the same change that must guarantee "no GPU execution."

## Consequences

- The Wan2.2 training execution layer is genuinely ready for a first GPU
  experiment in the sense that matters: every piece above the GPU
  boundary (config, dataset manifest, LoRA expert structure, checkpoint
  pairing, evaluation hooks, dispatch command-building) is real and
  tested, and the entrypoint script was actually run end-to-end during
  development (against a hand-built dataset manifest and the real
  `wan22_finetune.yaml` config), ending in a clean, correctly-reported
  `ModelUnavailableError` failure - not a crash, not a silent no-op.
- The remaining gap is exactly one thing, unchanged from ADR 0022's own
  stated gap: a real `IWan22TrainingBackend` implementation (wrapping
  `diffusers`/`musubi-tuner` against real GPU hardware and downloaded
  Wan2.2 weights). Nothing else in this layer needs to change when that
  lands - it implements the same two-method interface every other
  swap-point in this codebase uses.
- `run_experiment.py --dispatch` still does not actually invoke
  `dispatch_via_kaggle`/`dispatch_via_modal` end-to-end; that wiring is
  explicit follow-up work, not a hidden gap - see decision 9.
