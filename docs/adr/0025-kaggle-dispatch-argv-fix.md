# ADR 0025: Kaggle Dispatch Argv/Package/Weights Fix

**Status:** Accepted

## Context

While preparing the exact command for the first real GPU smoke run
(docs/EXECUTION_PLAN_FIRST_GPU_RUN.md), a real gap surfaced in ADR
0023's `dispatch_via_kaggle()`: a plain `kaggle kernels push` runs its
`code_file` with **no CLI arguments at all**. The original wiring pushed
`wan22_lora_train.py` directly as `code_file` - on a real Kaggle kernel
this would crash immediately on argparse's first required argument
(`--config`), because there is no way to pass `--config`/
`--dataset-manifest`/etc. to a Kaggle kernel the way
`TrainingCommand.to_argv()` assumes. Two further gaps compound this:
the `training` package (and `models/registry.yaml`, which lives at the
repo root, outside that package) isn't installed in Kaggle's default
kernel image; and Kaggle kernels have no persistent local disk between
runs, so real Wan2.2 weights can't simply be "already there."

This ADR fixes all three, for Kaggle only (Modal dispatch has a
separate, still-open gap - `ModalJobConfig`'s own docstring already
flags it: no `@app.function` named `train_wan22_lora` exists anywhere
in this codebase yet - out of scope here).

## Decisions

### 1. `dispatch_via_kaggle()` uploads a Kaggle dataset instead of relying on argv

The job's `config.yaml` + `dataset_manifest.jsonl` (already written to
disk by the existing `write_job_inputs()`) are copied into a staging
directory and uploaded as a real Kaggle dataset via the already-real
`KaggleClient.upload_dataset()` (ADR 0022) - one dataset per job,
slugged `<job_id>-input`. That dataset is attached to the kernel push
via `KernelPushConfig.dataset_sources` (already existed, was just never
used for this purpose), which Kaggle mounts read-only under
`/kaggle/input/<slug>/` at kernel runtime - the real substitute for CLI
arguments.

### 2. `kaggle_kernel_runner.py` replaces `wan22_lora_train.py` as the pushed `code_file`

`dispatch_via_kaggle()` now pushes a new wrapper
(`services/training/entrypoints/kaggle_kernel_runner.py`, pushed
alongside the entrypoint, same directory) as the kernel's `code_file`.
This wrapper does everything a real Kaggle kernel run needs, as real
subprocess calls (no sys.path/import tricks):

1. Shallow-clones this public repo into `/kaggle/working/repo` and
   `pip install -e`s `video-engine-sdk` + `training[gpu-training]` from
   it - solves the "package not installed" gap, and incidentally also
   solves the "`models/registry.yaml` isn't part of the pip package"
   gap, since the clone has it at its real repo-root path.
2. Checks a dataset is actually mounted under `/kaggle/input/` *before*
   doing anything expensive - fail fast on a misconfigured dispatch
   rather than after an 11GB download.
3. Runs the cloned repo's own real `download_wan22_weights.py` - solves
   the "no persistent disk" gap by downloading weights fresh inside
   each kernel run. `HF_TOKEN`, if ever needed, must be attached as a
   Kaggle Secret on the kernel (an environment variable), never
   hardcoded.
4. Runs the cloned repo's own real `wan22_lora_train.py --backend real`
   against the mounted config/manifest, writing output/checkpoints
   under `/kaggle/working/` - what `kaggle kernels output` (and the new
   `fetch_kaggle_kernel_result.py`, decision 3 below) downloads.

Verified for real in this sandbox up to the point its own network
restrictions block huggingface.co: with `clone=False` pointed at this
checked-out repo, the wrapper correctly fails fast when no dataset is
mounted, and correctly reaches (and fails at) the real
`download_wan22_weights.py` subprocess call otherwise - proving the
orchestration order and argument-wiring are correct, not the network
call itself (untestable here, no HF access - see
docs/EXECUTION_PLAN_FIRST_GPU_RUN.md).

### 3. `fetch_kaggle_kernel_result.py`: the missing "get the result back" step

Wraps the already-real, already-tested
`KaggleClient.poll_kernel_until_terminal()`/`pull_kernel_output()` (ADR
0022) as a CLI step - polls a pushed kernel until it reaches a terminal
status, then downloads its `/kaggle/working/` output (checkpoints) to a
local directory. This closes the loop `dispatch_via_kaggle()` opens:
push, wait, fetch.

## Consequences

- `dispatch_via_kaggle()`'s public signature changed
  (`dataset_sources` → `dataset_owner_slug`/`extra_dataset_sources`,
  since the function now builds its own required input dataset rather
  than accepting one from the caller) - `run_experiment.py`'s call site
  needed no changes (it never passed `dataset_sources`).
- Real Kaggle GPU cost per smoke run now includes downloading ~11GB of
  weights on every single kernel run (no caching across runs) - this is
  the honest cost of Kaggle's no-persistent-disk model, not something
  this fix could avoid without Kaggle's own dataset/model versioning
  (a possible future optimization, not built here).
- Modal dispatch remains non-functional (separate gap, not fixed by
  this ADR) - the CI workflow this unblocks targets Kaggle only.
