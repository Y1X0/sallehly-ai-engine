# services/training

## Training (custom foundation model track)

**Responsibility:** everything needed *before* the first real GPU
training run for the Sallehly custom video model - the dataset
pipeline, model registry, evaluation framework, and training
configuration this ADR calls "Phase 9 Preparation" (see
`docs/adr/0021-phase9-preparation.md` and
`docs/adr/0001-director-engine-separation.md`). Real training itself
(fine-tuning/LoRA runs against actual GPU hardware) is still Phase 9 and
has not started.

**Status:** Phase 9 Preparation implemented. Every module here is real,
CPU-only Python - no GPU, no model download, no training execution
anywhere:

- `config.py` - `TrainingConfig`/`LoRAConfig` (validated, YAML
  round-trippable) and `BASE_MODEL_REGISTRY` (real, web-search-verified
  license facts for Wan2.1/HunyuanVideo/CogVideoX/Stable Video
  Diffusion/Wan2.2 - `wan2.2-ti2v-5b`, `wan2.2-t2v-a14b`, `wan2.2-i2v-a14b`).
- `trainer.py` - `ITrainer` + `DryRunTrainer`, proving the
  step/checkpoint/eval-hook loop shape with zero GPU.
- `checkpoint.py` - `ICheckpointStore` + `InMemoryCheckpointStore`/
  `FilesystemCheckpointStore`.
- `dataset/` - `DatasetManager`: real `ffprobe`-based metadata
  extraction + SHA-256 content hashing, `DatasetValidator`,
  `HeuristicCaptionProvider` (real) / `VLMCaptionProvider` (raises
  `ModelUnavailableError`), `HashDuplicateDetector` (real) /
  `EmbeddingDuplicateDetector` (raises `ModelUnavailableError`),
  deterministic hash-based train/val/test split, dataset statistics,
  and content-addressable dataset versioning.
- `registry/` - `IModelRegistry` + `FilesystemModelRegistry`: a
  `STAGING -> CANARY -> PRODUCTION` promotion state machine,
  compatibility validation against a real
  `video_engine_sdk.CapabilityManifest`, and rollback.
- `evaluation/` - `BenchmarkRunner` (genuinely executes
  `IVideoEngine`/`IComputeProvider`, zero GPU needed with
  `Wan21Adapter`+`LocalProvider`), classical metrics (real) plus
  `FVDMetric`/`CLIPScoreMetric` (raise `ModelUnavailableError`), human
  evaluation store, `QualityReport`, `RegressionDetector`.
- `configs/` - four ready-to-use `TrainingConfig` YAML files, one per
  candidate base model.
- `automation/` - the zero/near-zero-cost training-factory automation
  layer (see `docs/adr/0022-training-automation-layer.md`):
  `KaggleClient` (real `kaggle` CLI wrapper - dataset upload/download,
  kernel push/status/output, polling), `ModalJobLauncher` (real `modal`
  CLI wrapper - job launch, GPU selection via `GPUType`, log fetch,
  wall-clock shutdown enforcement), `CostGuard` (`ApprovalRecord` +
  `UsageRecord` ledgers - the single choke point every paid-GPU dispatch
  must pass, both approval- and budget-gated), and
  `TrainingController`/`ExperimentConfigGenerator`/`ResultReporter` (AI
  training controller: plans experiments within human-set guardrail
  ranges, tracks job status, reports results).

**Automation entrypoints:** `services/training/scripts/run_experiment.py`
(plans an experiment; `--tier paid_gpu` requires a prior approval) and
`authorize_paid_job.py` (records a human's approval) are the CLI scripts
three GitHub Actions workflows invoke:
`.github/workflows/training-phase1-dataset-validation.yml` (CPU only,
push/PR-triggered, $0), `training-phase2-free-gpu-experiment.yml`
(scheduled + manual, Kaggle/Modal free tier, $0),
`training-phase3-paid-gpu-gate.yml` (manual only, gated by a GitHub
Environment's required reviewers - the only workflow that can plan a
paid job).

- `wan22/` - the real Wan2.2 training execution layer (see
  `docs/adr/0023-wan22-training-execution-layer.md`):
  `Wan22DatasetAdapter` (real `ClipRecord` -> `Wan22ManifestEntry`
  manifest, refuses uncaptioned/rights-uncleared clips),
  `Wan22LoRAConfig` (expert set derived from `base_model_id` -
  `{"unified"}` for TI2V-5B, `{"high_noise","low_noise"}` for either
  A14B variant - there is no way to construct one that fine-tunes an
  A14B model's experts separately), `Wan22CheckpointWriter`
  (`get_paired_checkpoints()` is a real integrity check, not
  documentation), `Wan22LoRATrainer(ITrainer)` (every configured expert
  trains on every step, never independently), `Wan22EvaluationHook`
  (real `BenchmarkRunner` wiring - proven against `Wan21Adapter` and the
  untrained `SallehlyModelAdapter`), and `dispatch_via_kaggle`/
  `dispatch_via_modal` (real `KaggleClient`/`ModalJobLauncher` wiring via
  a shared `TrainingCommand`). The one real execution boundary,
  `IWan22TrainingBackend`, has exactly one implementation
  (`UnavailableWan22Backend`) that always raises `ModelUnavailableError` -
  `services/training/entrypoints/wan22_lora_train.py` was actually run
  end-to-end during development and correctly fails there, with no
  partial/corrupt state left behind.

Real dispatch through `run_experiment.py --dispatch` is deliberately not
wired to `dispatch_via_kaggle`/`dispatch_via_modal` yet (ADR 0023
decision 9) - both are proven directly via unit tests with injected fake
CLI runners instead, so no code path in this repo can attempt a real
`kaggle`/`modal` CLI invocation today.

When real training starts, its eventual output is a new `IVideoEngine`
implementation living in
`services/video-engine-adapter/src/video_engine_adapter/adapters/`
(`SallehlyModelAdapter` already exists there, registered as
`sallehly-v1`, but has no trained weights) - following the exact same
contract `Wan21Adapter` implements today. See `docs/DEV_SETUP.md`
section 3e/3f/3g for runnable examples, and
`tests/test_training_framework.py`/`tests/test_training_dataset.py`/
`tests/test_training_registry.py`/`tests/test_training_evaluation.py`/
`tests/test_training_configs.py`/`tests/test_training_automation.py`/
`tests/test_training_wan22.py` for full coverage (226 tests).
