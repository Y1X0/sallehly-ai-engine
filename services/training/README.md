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

When real training starts, its eventual output is a new `IVideoEngine`
implementation living in
`services/video-engine-adapter/src/video_engine_adapter/adapters/`
(`SallehlyModelAdapter` already exists there, registered as
`sallehly-v1`, but has no trained weights) - following the exact same
contract `Wan21Adapter` implements today. See `docs/DEV_SETUP.md`
section 3e for runnable examples, and
`tests/test_training_framework.py`/`tests/test_training_dataset.py`/
`tests/test_training_registry.py`/`tests/test_training_evaluation.py`/
`tests/test_training_configs.py` for full coverage (133 tests).
