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
  Diffusion).
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
paid job). Real dispatch (`--dispatch`) is deliberately not wired to
anything yet - it needs a training entrypoint script this repo doesn't
ship (writing one is Phase 9 execution, not automation infrastructure).

When real training starts, its eventual output is a new `IVideoEngine`
implementation living in
`services/video-engine-adapter/src/video_engine_adapter/adapters/`
(`SallehlyModelAdapter` already exists there, registered as
`sallehly-v1`, but has no trained weights) - following the exact same
contract `Wan21Adapter` implements today. See `docs/DEV_SETUP.md`
section 3e/3f for runnable examples, and
`tests/test_training_framework.py`/`tests/test_training_dataset.py`/
`tests/test_training_registry.py`/`tests/test_training_evaluation.py`/
`tests/test_training_configs.py`/`tests/test_training_automation.py`
for full coverage (177 tests).
