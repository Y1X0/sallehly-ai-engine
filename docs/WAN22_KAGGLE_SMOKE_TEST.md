# Wan2.2 TI2V-5B Kaggle Smoke Test (GitHub Actions)

Operational guide for `.github/workflows/training-phase2-free-gpu-experiment.yml`'s
`wan22-ti2v5b-kaggle-smoke-test` job. For the technical story of why
this job exists in its current shape, see
docs/adr/0025-kaggle-dispatch-argv-fix.md and
docs/EXECUTION_PLAN_FIRST_GPU_RUN.md.

**This job trains on the real Stage 0 `multi_entity_interaction` clips**
(`dataset/sources/stage0_urls_multi_entity.json`, 9 real, rights-cleared
Wikimedia Commons videos - see `dataset/sources/stage0_sources.md` and
`docs/DATASET_SPEC.md`), fetched directly inside the runner (GitHub-hosted
runners have real internet access). It is still Stage 0/mechanism-proof
scope, not the full 600-clip Dataset v1 - see the workflow file's own
top-of-file note for exactly what license verification has and hasn't
been done at this stage. `max_train_steps: 20` in the generated scratch
config keeps this a short, cheap first real signal ("does training
change the model's behavior at all"), not a full training run.

## Required secrets

Add these under **Settings → Secrets and variables → Actions → Repository secrets**.
Nobody but a repo admin can do this - Claude (or any CI job) cannot add
secrets to the repository itself.

| Secret | Required | Where to get it |
|---|---|---|
| `KAGGLE_USERNAME` | Yes | kaggle.com/settings → API → "Create New Token" → downloads `kaggle.json` (contains both fields) |
| `KAGGLE_API_TOKEN` | Yes | kaggle.com/settings/api → "Generate New Token" → a `KGAT_...` access token. **Not** the older `KAGGLE_KEY` from a downloaded `kaggle.json` - `infra/kaggle/README.md` confirmed by hand that Kaggle's current API token flow no longer authenticates reliably through that older pair; this workflow uses the same fix `kaggle-free-inference.yml` already relies on. |
| `HF_TOKEN` | Only if `Wan-AI/Wan2.2-TI2V-5B-Diffusers` is or becomes gated (public as of this writing) | huggingface.co → Settings → Access Tokens |

If `KAGGLE_USERNAME`/`KAGGLE_API_TOKEN` are already configured as repo
secrets (they are, if `kaggle-free-inference.yml`'s real Kaggle GPU
inference runs have been working - same secrets, same names), this
workflow needs no new secret setup at all.

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
weights, fetches + ingests the real 9-clip `multi_entity_interaction`
Stage 0 dataset, dispatches a Kaggle kernel, polls it (up to 90
minutes), and uploads the resulting checkpoint + a markdown report as
a single workflow artifact named `wan22-ti2v5b-kaggle-smoke-<run_id>`.

## Training against a different or larger real dataset

The workflow currently fetches whatever URLs are in
`dataset/sources/stage0_urls_multi_entity.json`. Two ways to change
what it trains on:

### Option A: edit the JSON manifest, stay inside GitHub Actions

Add/replace URLs in `dataset/sources/stage0_urls_multi_entity.json`
(or point the "Fetch the real ... Stage 0 clips" step at a different
`--urls` file for another category) - every step after it already
works unchanged against whatever `fetch_stage0.py` downloads into
`dataset/raw/`. Only Wikimedia Commons/NASA URLs are supported by
`fetch_stage0.py` today (see `dataset/sources/fetch_stage0.py`'s own
`resolve()`); a different source needs its own resolver added there.

### Option B: run outside CI, on your own machine

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

### Option C: adapt the fetch step for a non-Wikimedia/NASA source

If real clips live somewhere `fetch_stage0.py` doesn't support (a
private object-storage bucket, a separate private data repo, etc.),
edit the **"Fetch the real ... Stage 0 clips"** step in
`training-phase2-free-gpu-experiment.yml` to fetch from there instead -
every step after it (`ingest_dataset.py` onward) already works
unchanged against whatever ends up in `dataset/raw/`. This requires
adding whatever additional secret your storage provider needs,
following the same "repository secret, never hardcoded" pattern as
`KAGGLE_USERNAME`/`KAGGLE_API_TOKEN` above.

Whichever option you use, remember `--rights-cleared` on
`ingest_dataset.py` is a real assertion, not a formality - only pass it
when every clip actually has a documented, auditable rights chain.
