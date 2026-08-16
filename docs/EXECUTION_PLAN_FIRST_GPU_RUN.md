# Execution Plan: First Real Wan2.2 GPU Training Experiment

Status: **planning document, not an authorization to spend money.** No
paid training has been started. Read this, run the smoke test, then
decide.

This plan covers the path from where the repository stands today
(docs/adr/0024-wan22-real-training-backend.md - real training mechanism,
no weights downloaded, no real dataset, no dispatch attempted) to a
first real, controlled GPU experiment.

## 0. Gate: run the smoke test first (already possible, $0, done in this change)

```
uv sync --all-packages --extra gpu-training
python services/training/scripts/run_smoke_test.py --base-model-id wan2.2-ti2v-5b
python services/training/scripts/run_smoke_test.py --base-model-id wan2.2-t2v-a14b
```

Both were run and passed during this change (real `WanTransformer3DModel`
+ real `peft` LoRA + real forward/backward/optimizer step + real paired
checkpoint save, at toy scale, on CPU). This proves the *mechanism*; it
proves nothing about real Wan2.2 output quality. Do not skip this step
in your own environment before proceeding - if it fails there, nothing
downstream will work either.

## 1. Required secrets / credentials

None of these exist in this repository or its CI. All must be
provisioned by a human, outside of any commit:

| Secret | Where it's used | Required for |
|---|---|---|
| `HF_TOKEN` | `download_wan22_weights.py` -> `huggingface_hub.snapshot_download` | Only if the target HF repo (`Wan-AI/Wan2.2-*-Diffusers`) is or becomes gated. Public as of this writing - verify on the repo's HF page before assuming it's not needed. |
| `KAGGLE_USERNAME` / `KAGGLE_KEY` (`~/.kaggle/kaggle.json`) | `KaggleClient` (`training.automation.kaggle_client`) | Free-tier GPU dispatch via `run_experiment.py --dispatch --provider kaggle` |
| `MODAL_TOKEN_ID` / `MODAL_TOKEN_SECRET` (`modal token set`) | `ModalJobLauncher` | Free-tier GPU dispatch via `--provider modal` |
| `RUNPOD_API_KEY` / `RUNPOD_ENDPOINT_ID` | Only relevant for real Wan2.1/Wan2.2 *inference* via `RunPodProvider` (`services/video-engine-adapter`), not training dispatch - training dispatch only supports kaggle/modal (ADR 0024 decision 8) | Not required for the training path itself; required once a trained checkpoint is served |
| GitHub Environment `paid-gpu-approval` reviewers | `.github/workflows/training-phase3-paid-gpu-gate.yml` | Any `ExperimentTier.PAID_GPU` job - unchanged from ADR 0022, still the only path to a paid job |
| `TRAINING_MONTHLY_BUDGET_USD` (GH Actions variable) | `CostGuard` | Paid-tier spend ceiling - currently defaults to `50` if unset; set explicitly to your real budget |

## 2. Expected storage

| Item | Size | Notes |
|---|---|---|
| `wan2.2-ti2v-5b` weights | ~11 GB | `models/registry.yaml`'s `download.approx_download_size_gb` - transformer + VAE + text encoder + tokenizer, Diffusers format |
| `wan2.2-t2v-a14b` weights | ~58 GB | Two transformer experts (`transformer/` + `transformer_2/`) + VAE + text encoder |
| First real dataset (raw clips) | order of 1-10 GB | Depends entirely on clip count/length/resolution you actually ingest - not estimable in the abstract; check with `du -sh` after `ingest_dataset.py` |
| LoRA checkpoints | tens of MB each | `peft` saves adapter-only weights (`adapter_model.safetensors` + `adapter_config.json`), not the base model - a rank-16 LoRA over a 5B model is on the order of tens of MB, not gigabytes |
| Total for a first TI2V-5B LoRA run | **~15-25 GB** | Weights + a modest first dataset + a handful of checkpoints |

Sizes above are taken from `models/registry.yaml`'s recorded estimate,
itself checked against the repo's stated file layout on 2026-07-26, not
independently downloaded in this sandbox (no GPU/disk budget for a
multi-GB download here) - re-verify the actual downloaded size against
`du -sh .models-cache/wan2.2-ti2v-5b` after a real run of
`download_wan22_weights.py`.

## 3. Expected GPU cost

| Tier | Provider | Cost | Notes |
|---|---|---|---|
| Smoke test | local CPU | **$0** | Already run - see step 0 |
| Free GPU experiment (Phase 2) | Kaggle (T4x2/P100) | **$0** | ~30 GPU-hrs/week free quota; `ExperimentTier.FREE_GPU`, no `CostGuard` gate |
| Free GPU experiment (Phase 2) | Modal (T4/L4/A10G) | **$0** up to ~$30/month free credit | Real per-second billing beyond that - `ModalJobLauncher.enforce_wall_clock_ceiling` is the safety net against a hung job overrunning it |
| First real paid experiment (Phase 3) | RunPod/similar, e.g. RTX 4090 or A10G on-demand | rough estimate **$3-15** for a short (500-1500 step) TI2V-5B LoRA run at $0.30-0.75/hr rented, several hours wall clock | **Unverified estimate** - no real step timing exists yet in this environment (no GPU here). Measure the smoke test's real analog: run 50-100 real steps on your actual rented GPU first, then extrapolate linearly before approving a longer run. |

Whatever number you land on for a real paid run must be passed as
`--estimated-cost-usd` to `authorize_paid_job.py`/`run_experiment.py
--tier paid_gpu`, and stays hard-capped by `CostGuard` (ADR 0022,
unchanged) - it cannot silently run over either the per-job approval or
the monthly budget.

## 4. Expected training time

**Not independently measured in this sandbox** (no GPU available here).
Rough, unverified guidance from the config's own notes
(`services/training/configs/wan22_finetune.yaml`): TI2V-5B LoRA at
960x544/81 frames with fp8 + block-swap has been reported by the
musubi-tuner community to fit in 16-24GB VRAM - but per-step wall time
depends on the specific GPU, resolution, and frame count actually used.

**Do this instead of trusting a guessed number:** run the first 50-100
real steps on your actual target GPU (this is exactly what the Phase 2
free-tier lane, `--tier free_gpu`, is for), read the real wall-clock
time per step from the entrypoint's own step-by-step log output
(`wan22_lora_train.py` already prints `step N/max_train_steps` per
step), and multiply out to `max_train_steps` before deciding on a paid,
longer run.

## 5. Recommended sequence

1. Run the smoke test locally (step 0) - already done, $0.
2. `download_wan22_weights.py --engine-id wan2.2-ti2v-5b` on the machine
   that will actually train (not in CI).
3. `ingest_dataset.py --clips-dir <real clips> --rights-cleared
   --base-model-config services/training/configs/wan22_finetune.yaml`
   - produces a real `dataset_version` and manifest.
4. Update `services/training/configs/wan22_finetune.yaml`'s
   `dataset_version` from `REPLACE_WITH_REAL_DATASET_VERSION_ID` to the
   real id step 3 printed.
5. `wan22_lora_train.py --backend real --config
   services/training/configs/wan22_finetune.yaml --dataset-manifest
   <manifest from step 3> ...` directly on your GPU machine for a short
   run (e.g. `max_train_steps: 50`) to get a real step-time measurement -
   still free if run on a Kaggle/Modal free-tier GPU.
6. Only after step 5 gives you a real cost/time number: request a
   Phase 3 paid-GPU run via `authorize_paid_job.py` +
   `run_experiment.py --tier paid_gpu` with an honest
   `--estimated-cost-usd`, requiring human approval through the
   `paid-gpu-approval` GitHub Environment (unchanged, ADR 0022).

No step in this plan has been executed beyond step 0 (the smoke test).
