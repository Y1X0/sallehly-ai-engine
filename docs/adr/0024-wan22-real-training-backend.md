# ADR 0024: Wan2.2 Real Training Backend, Weights Download, Dataset Ingestion, and Dispatch Wiring

**Status:** Accepted

## Context

ADR 0023 shipped the Wan2.2 training *execution layer* deliberately
unable to execute anything real: `UnavailableWan22Backend` was the only
`IWan22TrainingBackend`, `run_experiment.py --dispatch` refused to run
because no training entrypoint existed, no Wan2.2 weights had ever been
fetched, and no dataset had ever been turned into a real
`dataset_version`. This ADR closes those gaps - moving from "preparation
phase" into "first real AI execution phase" per explicit instruction -
while keeping every existing public interface (`IVideoEngine`,
`IComputeProvider`, `TrainingController`, `DatasetManager`,
`IModelRegistry`) unchanged, and without starting any paid GPU training.

## Decisions

### 1. Real ML dependencies are an optional extra, not a base dependency

`torch`, `diffusers`, `transformers`, `accelerate`, `peft`, `safetensors`,
`huggingface_hub`, `imageio`, `imageio-ffmpeg` are added to
`services/training/pyproject.toml` under `[project.optional-dependencies]
gpu-training`, not `dependencies`. `training-phase1-dataset-validation.yml`
runs `uv sync --all-packages` on every push/PR and must stay fast,
CPU-only, and $0 as designed (ADR 0022) - it does not install this
extra. Only a real training run (or the smoke test) needs
`uv sync --all-packages --extra gpu-training`.

### 2. `Wan22DiffusersBackend`: the real `IWan22TrainingBackend`, verified against the installed library before being written

Rather than guess at `diffusers`' Wan2.2 API surface, the actual
installed classes (`diffusers==0.39.0`, `peft==0.19.1`, `torch==2.13.0`)
were introspected and exercised end-to-end (tiny `WanTransformer3DModel`
+ `peft.get_peft_model` + forward/backward/`AdamW.step()`/
`save_pretrained`) in an isolated venv before this class was committed -
this mechanism is proven to work, not assumed. Key facts this
confirmed:

- `WanTransformer3DModel.forward(hidden_states, timestep,
  encoder_hidden_states, ...)` - `hidden_states` shape
  `(batch, channels, frames, height, width)`, matching
  `AutoencoderKLWan`'s latent conventions.
- `WanPipeline.__init__` takes `transformer` and `transformer_2` -
  confirming the real HF Diffusers-format repo layout
  (`transformer/`/`transformer_2/` subfolders) maps exactly onto this
  codebase's existing `EXPERT_HIGH_NOISE`/`EXPERT_LOW_NOISE` split
  (ADR 0023) for the A14B MoE variants, and a single `transformer/` for
  the unified TI2V-5B variant.
- `peft.get_peft_model(model, LoraConfig(target_modules=["to_q", "to_k",
  "to_v", "to_out.0"]))` attaches cleanly to `WanTransformer3DModel` -
  the exact `target_modules` default `training.lora.LoRAConfig` already
  used, unchanged.

The transformer forward/backward/optimizer/checkpoint mechanism is
fully real and verified. Two things are real code but *not* verified
against real weights (no GPU or multi-GB weights exist in this
sandbox): the flow-matching loss formulation (a standard rectified-flow
`target = noise - sample` objective, not a byte-for-byte reimplementation
of `FlowMatchEulerDiscreteScheduler`), and `DiffusersBatchEncoder`'s real
VAE/text-encoder path. Both are flagged in their own docstrings as
needing a real-clip sanity check before a production run.

### 3. `RandomLatentBatchEncoder`: real shapes, synthetic values - until real weights exist

The transformer needs `hidden_states`/`encoder_hidden_states` tensors;
producing them for real requires a real VAE + text encoder (i.e. real
downloaded weights). Rather than block the entire backend on that,
`RandomLatentBatchEncoder` computes the *real* latent shape from a
manifest entry's *real* width/height/num_frames (via Wan2.2's real
VAE spatial/temporal downsample factors) and fills it with seeded
random values - the same "prove the mechanism, not the expensive
resource" posture `DryRunTrainer`/`LocalProvider`/
`HeuristicCaptionProvider` already established elsewhere in this
codebase. `DiffusersBatchEncoder` is the real replacement, swapped in
once real weights are downloaded and a real clip is available.

### 4. `build_smoke_test_backend()`: the same real classes, at toy scale

A `WanTransformer3DModel` with `num_layers=1`, `attention_head_dim=16`,
etc. (~20K params) is still a real instance of the real class - LoRA
injection, forward, backward, optimizer step, and `save_pretrained` all
run through the identical code path a real 5B/14B run would. This is
what "controlled smoke test" means here: not a mock, a real mechanism
at a scale that runs on CPU in well under a second. It does not, and
cannot, validate real Wan2.2 output quality.

### 5. `models/registry.yaml` gains `wan2.2-ti2v-5b`/`wan2.2-t2v-a14b` entries with `status: training-target`

Distinct from `wan2.1`'s `status: primary` - these are not yet a
selectable `IVideoEngine` (no adapter implements `IVideoEngine` against
them; `Wan22DiffusersBackend` only trains a LoRA adapter on top of
them). Each entry's `experts:` block maps expert name to HF repo
subfolder (`transformer`/`transformer_2`), its `download:` block is
what `training.hf_download` consumes, and `checkpoints.lora_adapters_root`
records where trained LoRA adapters land. `training.wan22.registry_metadata`
validates this structure (which experts, valid HF repo id shape,
required fields) independently of `registry.compatibility.validate_capability_manifest`
(which validates the *capability envelope*, not the *training metadata*)
- two different concerns, two different validators, `IModelRegistry`
itself untouched.

### 6. `training.hf_download`: real `snapshot_download`, real per-file SHA-256, injectable for tests

Mirrors `KaggleClient`/`ModalJobLauncher`'s `runner`-injection pattern:
`HuggingFaceWeightsDownloader(download_fn=...)` lets tests exercise the
full download -> manifest -> verify -> corruption-detection flow
without any network access or multi-GB download (verified with an
injected fake in this session). Real downloads are never automated in
CI (weights are multi-GB, and don't belong in GitHub Actions) - a human
runs `services/training/scripts/download_wan22_weights.py` once, on the
machine that will actually train.

### 7. `services/training/scripts/ingest_dataset.py`: the first real `dataset_version`

Wires the already-real `DatasetManager` pipeline (ffprobe ingest,
heuristic captioning, validation, deterministic split, content-addressable
versioning - all built in Phase 9 Preparation, ADR 0021) into one CLI a
human runs once against a real clips directory, ending with a real
`dataset_version` id to paste into `TrainingConfig.dataset_version`
(replacing the `REPLACE_WITH_REAL_DATASET_VERSION_ID` placeholder every
config ships with) and a Wan2.2 manifest JSONL per split.
`--rights-cleared` is a required, no-default flag - this script will not
silently assume the answer to a real legal question.

### 8. `run_experiment.py --dispatch` now actually dispatches (kaggle/modal only)

Requires `--dataset-manifest` (built by `ingest_dataset.py`); copies it
to the `TrainingCommand`'s derived path, writes the job's config, and
calls the real `dispatch_via_kaggle`/`dispatch_via_modal` (ADR 0023) -
unchanged functions, now actually reached. Only `provider=kaggle` and
`provider=modal` are supported, since those are the only two providers
this repository has a real automation client for (`fal`/`runpod`/`vastai`
dispatch remains unimplemented and fails fast, not silently). The
PAID_GPU `CostGuard` approval+budget gate (ADR 0022) runs exactly as
before, upstream of dispatch - nothing about the cost-protection
mechanism changed.

### 9. Interfaces named in this task's instructions are unchanged

`IVideoEngine`, `IComputeProvider`, `TrainingController`,
`DatasetManager`, `IModelRegistry` gained no new methods and no changed
signatures. Everything above is new classes/functions/scripts calling
into them, or a new `IWan22TrainingBackend` implementation alongside
(not replacing) `UnavailableWan22Backend`.

## Consequences

- Real training can now genuinely execute, once (a) real weights are
  downloaded via `download_wan22_weights.py`, (b) a real dataset is
  ingested via `ingest_dataset.py`, and (c) a real GPU environment (a
  rented Kaggle/Modal/RunPod instance) runs `wan22_lora_train.py
  --backend real`.
- `wan22_lora_train.py --backend auto` (the new default) still runs to
  a real, tiny-scale completion with zero setup - the controlled smoke
  test this task required before any paid experiment.
- What remains manual, by design, not automated: the actual weight
  download and dataset ingestion (both real, human-triggered CLI runs,
  not CI jobs - see docs/EXECUTION_PLAN_FIRST_GPU_RUN.md), Kaggle/Modal/
  HF credential provisioning, and the human approval step for any
  PAID_GPU job (unchanged from ADR 0022).
