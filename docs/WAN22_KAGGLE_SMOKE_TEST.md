# Wan2.2 TI2V-5B Kaggle Smoke Test (GitHub Actions)

Operational guide for `.github/workflows/training-phase2-free-gpu-experiment.yml`'s
`wan22-ti2v5b-kaggle-smoke-test` job. For the technical story of why
this job exists in its current shape, see
docs/adr/0025-kaggle-dispatch-argv-fix.md and
docs/EXECUTION_PLAN_FIRST_GPU_RUN.md.

**This job is development/pipeline-verification only.** It generates a
placeholder dataset (solid-color test clips) purely to prove the
mechanism - dataset ingestion, weight download, real LoRA training,
checkpointing - runs end to end on a real free Kaggle GPU. The
resulting checkpoint has no real quality. It is not, and is not meant
to be, a real training run.

## Required secrets

Add these under **Settings → Secrets and variables → Actions → Repository secrets**.
Nobody but a repo admin can do this - Claude (or any CI job) cannot add
secrets to the repository itself.

| Secret | Required | Where to get it |
|---|---|---|
| `KAGGLE_USERNAME` | Yes | kaggle.com/settings → API → "Create New Token" → downloads `kaggle.json` (contains both fields) |
| `KAGGLE_KEY` | Yes | same `kaggle.json` file |
| `HF_TOKEN` | Only if `Wan-AI/Wan2.2-TI2V-5B-Diffusers` is or becomes gated (public as of this writing) | huggingface.co → Settings → Access Tokens |

No secret value is ever printed by this workflow; GitHub Actions also
automatically masks any string matching a configured secret's value in
the log output.

## How to manually trigger the smoke test

1. GitHub → **Actions** tab → select **"Training - Phase 2 Free GPU Experiment (Kaggle/Modal, $0)"** in the left sidebar.
2. Click **"Run workflow"**.
3. Check **`run_wan22_kaggle_smoke_test`** — this box must be checked; without it, the run only executes the existing `plan-experiment` job (unaffected by anything in this document) and does nothing real.
4. Fill in **`kaggle_username`** with your real Kaggle username (not necessarily your GitHub username - these are independent accounts).
5. Click **"Run workflow"** to start it.

This job never fires from the nightly schedule and never fires from a
plain "Run workflow" click that leaves the checkbox unset - a real GPU
run only happens when a human explicitly opts in on that specific run.

What happens next: the job downloads ~11GB of real Wan2.2 TI2V-5B
weights, generates + ingests the placeholder dataset, dispatches a
Kaggle kernel, polls it (up to 90 minutes), and uploads the resulting
checkpoint + a markdown report as a single workflow artifact named
`wan22-ti2v5b-kaggle-smoke-<run_id>`.

## Replacing the placeholder dataset with a real one

GitHub-hosted runners cannot see files on your own machine, so this
workflow cannot ingest your real footage directly. To train against a
real dataset instead of the placeholder clips, you have two options:

### Option A (recommended first): run outside CI, on your own machine

This is the path already covered by
docs/EXECUTION_PLAN_FIRST_GPU_RUN.md:

```bash
uv sync --all-packages --extra gpu-training

python services/training/scripts/download_wan22_weights.py --engine-id wan2.2-ti2v-5b

python services/training/scripts/ingest_dataset.py \
  --clips-dir /path/to/your/real/clips --rights-cleared \
  --base-model-config services/training/configs/wan22_finetune.yaml
# copy the printed dataset_version into wan22_finetune.yaml

python services/training/entrypoints/wan22_lora_train.py \
  --backend real \
  --config services/training/configs/wan22_finetune.yaml \
  --dataset-manifest .training-data/manifests/<version>_train.jsonl \
  --output-dir .training-runs/real/output \
  --checkpoint-store-dir .training-runs/real/checkpoints \
  --job-id first-real-run
```

You can also dispatch this to Kaggle from your own machine (same
credentials, no GitHub Actions involved):

```bash
python services/training/scripts/run_experiment.py \
  --base-config services/training/configs/wan22_finetune.yaml \
  --allowed-ranges services/training/automation/allowed_ranges.example.json \
  --tier free_gpu --provider kaggle --dispatch \
  --dataset-manifest .training-data/manifests/<version>_train.jsonl \
  --kaggle-kernel-ref <your-kaggle-username>/wan22-real-run

python services/training/scripts/fetch_kaggle_kernel_result.py \
  --kernel-ref <your-kaggle-username>/wan22-real-run \
  --output-dir ./kaggle-output
```

### Option B: adapt this CI workflow to fetch your real clips

If you want the whole pipeline to stay inside GitHub Actions, edit the
**"Generate a DEVELOPMENT-ONLY placeholder dataset"** step in
`training-phase2-free-gpu-experiment.yml` to fetch your real clips from
wherever they're actually stored (a private object-storage bucket, a
separate private data repo, etc.) instead of running `ffmpeg` - every
step after it (`ingest_dataset.py` onward) already works unchanged
against whatever ends up in `/tmp/ci-placeholder-clips` (rename the
directory too, so its name stops claiming to be a placeholder once it
holds real data). This requires adding whatever additional secret your
storage provider needs, following the same "repository secret, never
hardcoded" pattern as `KAGGLE_USERNAME`/`KAGGLE_KEY` above.

Whichever option you use, remember `--rights-cleared` on
`ingest_dataset.py` is a real assertion, not a formality - only pass it
when every clip actually has a documented, auditable rights chain.
