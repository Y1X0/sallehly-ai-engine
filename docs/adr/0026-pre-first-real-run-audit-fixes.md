# ADR 0026: Pre-First-Real-Run Production Audit Fixes

**Status:** Accepted

## Context

A final, deliberately skeptical production audit of the Wan2.2 LoRA
training pipeline (docs/adr/0024, docs/adr/0025) - performed
specifically to answer "is this actually safe to run against a real
Kaggle GPU" rather than "does this look complete" - found several real
gaps that would have surfaced during, not before, the first real GPU
run. This ADR fixes all of them. No public interface changed signature
incompatibly; every change here is additive (new optional parameters
with safe defaults, new concrete-not-abstract methods, new CLI flags).

## Decisions

### 1. Real GPU execution is now enforced, not assumed

`wan22_lora_train.py --device` previously defaulted to `"cpu"`, and
`kaggle_kernel_runner.py` never overrode it - a real Kaggle GPU dispatch
could reach the training step and silently train on CPU the entire
time. Fixed two ways:

- `wan22_lora_train.py`'s `--device` now defaults to `"auto"`, resolved
  by a new `_resolve_device()` that requires `torch.cuda.is_available()`
  and fails immediately, with a clear error, if it's `False`. `--device
  cpu` remains available as an explicit, intentional opt-out. This only
  applies to the real backend - `--backend smoke-test` stays CPU-only
  regardless of `--device`, unchanged.
- `kaggle_kernel_runner.py` gained its own `_verify_cuda_available()`,
  checked before any clone/install/download work, and now passes
  `--device auto` explicitly to `wan22_lora_train.py` rather than
  omitting the flag.

### 2. Every RNG a training step draws from is now seeded

`TrainingConfig.seed` was accepted by `Wan22DiffusersBackend.__init__`
but never actually used to seed anything - `train_step()`'s noise/
timestep sampling and `peft`'s LoRA weight initialization both drew from
torch's unseeded global RNG, so two runs with the same seed produced
different results. Fixed with a new `_seed_everything(seed)` (python
`random`, `numpy`, `torch` CPU + CUDA generators), called from
`Wan22DiffusersBackend.__init__`. `build_real_backend()` gained a
`seed: int = 0` parameter (it had none at all before), and
`wan22_lora_train.py`'s `_build_backend()` now threads
`config.seed` through to both the real and smoke-test backend builders.

Separately, `RandomLatentBatchEncoder.encode()` used Python's built-in
`hash()` on `clip_id` to derive a per-clip seed - `hash()` on strings is
salted per-process by `PYTHONHASHSEED`, so this was not actually
reproducible across separate process launches despite looking seeded.
Replaced with `_stable_clip_seed()`, a `hashlib.sha256`-based derivation
that is stable everywhere.

No dataloader workers exist in this codebase (dataset batches are drawn
by a plain round-robin list index in `Wan22LoRATrainer.train()`, not a
`torch.utils.data.DataLoader`), so there was nothing to seed there.

### 3. Kaggle's preinstalled CUDA torch is never touched

`kaggle_kernel_runner.py` used to run
`pip install -e "services/training[gpu-training]"`, which asks pip to
resolve that extra's own `torch>=2.3` requirement - a real risk of pip
deciding to replace Kaggle's preinstalled, driver-matched CUDA torch
build with an unrelated one resolved from PyPI. Fixed by
`_install_missing_packages()`: the two local packages are installed
with `--no-deps`, and only whichever of the gpu-training extra's other
dependencies (diffusers, transformers, accelerate, peft, safetensors,
huggingface_hub, imageio, imageio-ffmpeg) aren't already importable are
installed explicitly by name, also `--no-deps` - `torch` is never named
in any pip invocation this script makes.

### 4. Checkpoint resume support

Added `IWan22TrainingBackend.load_checkpoint()` - concrete (not
abstract), defaulting to `NotImplementedError` so no existing backend
needed to change - and a real implementation on
`Wan22DiffusersBackend` that restores a saved LoRA adapter's state dict
into the (lazily-built) peft model for that expert.
`Wan22CheckpointWriter` gained `latest_paired_step()`, which finds the
highest step where every configured expert already has a saved
checkpoint (skipping any step where a prior run died mid-checkpoint and
only some experts got saved). `Wan22LoRATrainer.train()` now checks this
before its loop: if a paired checkpoint exists, it loads each expert's
saved state and continues `global_step` from there instead of
restarting at step 0 - `Wan22LoRATrainer.__init__`'s own signature did
not change.

Note on scope: this resume mechanism is fully real and tested at the
trainer/backend layer (same process or a fresh process pointed at the
same `--checkpoint-store-dir`/`--output-dir`). It does not yet give the
Kaggle free-tier CI smoke test cross-kernel-push resume, because each
`dispatch_via_kaggle()` push starts a brand-new kernel with an empty
`/kaggle/working/` (docs/adr/0025's "no persistent disk" limitation,
unchanged here) - there is no previous checkpoint for a fresh kernel to
find. This fix protects any run against a persistent
`--checkpoint-store-dir` (local iteration, or a future non-Kaggle
persistent GPU target), exactly as requested; it does not claim to
solve Kaggle's separate no-persistent-disk constraint.

### 5. Kaggle output is always fetched, even after a polling timeout

`fetch_kaggle_kernel_result.py` previously returned immediately if
`poll_kernel_until_terminal()` raised (including on a timeout) -
`pull_kernel_output()` was never called, discarding whatever logs/
checkpoints the kernel had already produced. Fixed: polling failures are
now caught and remembered, but `pull_kernel_output()` is always attempted
afterward regardless of whether polling succeeded, timed out, or the
kernel's terminal status was an error - the function still returns
non-zero in all of those cases, it just no longer skips the fetch step.

### 6. The CI placeholder dataset split can no longer produce zero training samples

The CI workflow's `ingest_dataset.py` step used the default
`val_fraction=0.1`/`test_fraction=0.1` against only 3 CI-generated
clips - `assign_split()`'s SHA-256 hash bucketing gives each clip a real
(small but nonzero) chance of landing outside "train", and with only 3
clips there was a real chance "train" ended up empty, breaking the next
step's `ls .training-data/manifests/*_train.jsonl`. Fixed by passing
`--val-fraction 0 --test-fraction 0` for this placeholder-data ingest
step specifically - `assign_split()`'s own bucket comparison guarantees
every clip lands in "train" when both fractions are 0. A held-out val/
test split is meaningless for a 3-clip mechanism check anyway; this
does not change `ingest_dataset.py`'s own defaults for real production
ingestion runs.

### 7. The fetched checkpoint is now validated, not just assumed to exist

`fetch_kaggle_kernel_result.py` gained `--validate-checkpoint`: after
pulling output, it globs for `adapter_model.safetensors` anywhere under
`--output-dir`, fails if none exist, and fails if any found file isn't
actually loadable via `safetensors.torch.load_file` or loads to an
empty state dict. The CI workflow now passes this flag, so a run that
"succeeded" (kernel completed, output pulled) but produced no usable
checkpoint - e.g. it crashed before its first `checkpoint_every_steps`,
or wrote a truncated file - now fails the workflow instead of reporting
success.

### 8. The Kaggle smoke-test job has a real time budget

`wan22-ti2v5b-kaggle-smoke-test` had no `timeout-minutes` - fixed by
setting `timeout-minutes: 120`, matched to the same order of magnitude
as `fetch_kaggle_kernel_result.py --timeout-sec 5400` (90 minutes) plus
setup/teardown headroom, so a genuinely stuck job doesn't run
indefinitely (and burn Actions minutes) even after
`poll_kernel_until_terminal()`'s own timeout is reached.

## Consequences

- `IWan22TrainingBackend`, `build_real_backend()`, `_build_backend()`
  (wan22_lora_train.py) all gained new parameters with backward-
  compatible defaults - no existing caller needed to change.
- `--device`'s default changed from `"cpu"` to `"auto"` - any existing
  script or docs example relying on the old silent-CPU default must now
  pass `--device cpu` explicitly if a CPU run of the *real* backend is
  actually intended (the CPU-only smoke-test path is unaffected either
  way).
- The CI placeholder-dataset ingest step's manifest no longer produces
  `*_val.jsonl`/`*_test.jsonl` files (0 entries each) - only
  `*_train.jsonl` - which is the correct outcome for a mechanism-only
  smoke test with real production ingestion unaffected.
