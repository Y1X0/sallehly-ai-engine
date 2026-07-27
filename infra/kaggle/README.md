# infra/kaggle

Real, free (no billing) deployment tooling for one Wan2.2 text-to-video
**inference** run on a real Kaggle GPU kernel (P100/T4x2). Inference-only
- this is deliberately not a training path (that already exists,
separately, in `services/training/automation` /
`.github/workflows/training-phase2-free-gpu-experiment.yml`). Nothing
in this directory is a new inference implementation: it dispatches the
platform's own, already-real `video_engine_adapter.inference.wan_inference.generate_video()`
(the same function `LocalInferenceProvider` and
`workers/gpu-worker/handler.py` call) to a real GPU for the first time,
via the same real `KaggleClient` the training path already uses.

## Files

- `kaggle_inference_kernel_runner.py` - the one script Kaggle actually
  runs (pushed as the kernel's `code_file`). Verifies a CUDA GPU is
  attached, clones this repo at a pinned git ref, installs only what's
  missing (never touches Kaggle's preinstalled CUDA-enabled torch),
  then calls `generate_video(..., smoke_test=False, device="cuda")` and
  writes a real `.mp4` under `/kaggle/working/output/`.
- `dispatch_inference.py` - builds the inference request
  (prompt/resolution/frames/etc.) and pushes the kernel above via the
  real `kaggle` CLI (`training.automation.kaggle_client.KaggleClient`).
- `fetch_inference_result.py` - polls the kernel until it finishes and
  downloads the real result: a `.mp4` + `metadata.json` on success, or
  a real `error.json` (the kernel's own caught exception - e.g. a CUDA
  OOM - never a bare "Internal error") on failure.

## Recommended: run via GitHub Actions

`.github/workflows/kaggle-free-inference.yml` runs dispatch + fetch for
you on a real GitHub-hosted runner. It needs no torch/diffusers install
on the runner itself - only the lightweight `kaggle` CLI (via
`uv run --with kaggle`) to talk to Kaggle's API; the actual GPU work
happens inside the dispatched kernel, on Kaggle's own machine.

**One-time setup**, before the first run - add these under
**Settings → Secrets and variables → Actions → Repository secrets**:

| Secret | Required | Where to get it |
|---|---|---|
| `KAGGLE_USERNAME` | Yes | kaggle.com/settings → API → "Create New Token" → downloads `kaggle.json` (contains both fields) |
| `KAGGLE_KEY` | Yes | same `kaggle.json` file |

Nobody but a repo admin can add secrets - this workflow (like every
other one in this repo) fails fast with a clear message if either is
missing, before doing any real work.

**To run it**: Actions → "Kaggle - Free GPU Wan2.2 Inference" → Run
workflow → fill in `prompt` → check `confirm_run` → Run (the Kaggle
account the kernel/dataset are pushed under comes from the
`KAGGLE_USERNAME` secret above - no need to type it again). It
dispatches a real Kaggle kernel, polls it (up
to 80 minutes - Wan2.2-TI2V-5B is ~11GB, plus load+generate time), and
uploads the real result (`video.mp4` + `metadata.json`, or `error.json`
on failure) as the run's workflow artifact.

## Manual alternative (your own machine, real Kaggle credentials)

```bash
export KAGGLE_USERNAME=...   # from kaggle.json
export KAGGLE_KEY=...        # from kaggle.json

uv run --with kaggle python infra/kaggle/dispatch_inference.py \
    --prompt "A calm lake at sunrise, gentle ripples, warm golden light" \
    --git-ref "$(git rev-parse --abbrev-ref HEAD)" \
    --kaggle-username your-kaggle-username
# -> prints: Kernel dispatched: your-kaggle-username/wan-inference-<ts>

uv run --with kaggle python infra/kaggle/fetch_inference_result.py \
    --kernel-ref your-kaggle-username/wan-inference-<ts> \
    --output-dir ./kaggle-inference-output
```

## Honest constraints - read before running

- **VRAM is a real, open question.** `models/wan2.2-ti2v-5b/capability_manifest.yaml`'s
  own `gpu_requirements.min_vram_gb` is 16 - Kaggle's free P100/T4 also
  have 16GB. This run uses plain bf16 full precision (no fp8/block-swap
  trick), the same as `generate_video()` already does everywhere else
  in this codebase. A real CUDA out-of-memory error is a legitimate,
  informative real result this tooling reports clearly via
  `error.json` - it is not a bug in this dispatch mechanism.
- **First trial defaults are deliberately small**: 17 frames (~1.06s @
  16fps) and 20 sampling steps (this engine's real default is ~40) -
  tunable via `dispatch_inference.py`'s CLI flags / the workflow's
  inputs, to reduce time/memory on the very first attempt.
- **Kaggle session limits**: free accounts get ~30 GPU-hours/week and a
  single session caps out around 9-12 hours - this workflow's 80-minute
  poll timeout is well inside that, but repeated runs share the same
  weekly quota.
- **Weights download**: `Wan-AI/Wan2.2-TI2V-5B-Diffusers` (~11GB) is
  downloaded fresh inside the kernel via `diffusers.WanPipeline.from_pretrained`
  every run (Kaggle kernels have no persistent disk between runs) - the
  same real, public (as of this writing) HF repo `workers/gpu-worker`
  uses, recorded in `models/registry.yaml`.
- **Never falls back to CPU or a mock.** Same fail-fast convention as
  every other real-GPU entrypoint in this codebase
  (`wan22_lora_train.py`, `wan_inference.py`'s own `_resolve_device`).

## Status

Real, working dispatch tooling, built additively (no changes to
`apps/`, `services/`, or `packages/` core code - only new files under
`infra/kaggle/` and one new GitHub Actions workflow). Not yet run for
real: `KAGGLE_USERNAME`/`KAGGLE_KEY` are not currently configured as
repository secrets (confirmed by actually triggering
`training-phase2-free-gpu-experiment.yml`'s Kaggle smoke test, which
failed at its own "Verify Kaggle authentication" step with exactly
that message - see `docs/PRODUCTION_READINESS_CHECKLIST.md` §0 for the
run id). Add the two secrets above, then run the workflow, to get the
first real result.
