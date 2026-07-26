from __future__ import annotations

import shutil
from pathlib import Path

from ..automation.controller import JobRecord
from ..automation.kaggle_client import (
    DatasetMetadata,
    KaggleClient,
    KaggleDatasetRef,
    KaggleKernelRef,
    KernelPushConfig,
)
from ..automation.modal_client import GPUType, ModalJobConfig, ModalJobHandle, ModalJobLauncher
from .command import TrainingCommand, build_training_command

_KAGGLE_RUNNER_FILENAME = "kaggle_kernel_runner.py"


def build_training_command_for_job(job: JobRecord, **kwargs) -> TrainingCommand:
    """Item 7: the bridge from `TrainingController`'s planning output (a
    `JobRecord`) to something dispatchable. Deliberately a plain
    function, not a `JobRecord` method or a `TrainingController` method -
    `services/training/automation` stays Wan2.2-agnostic (it already
    supports any base model's `TrainingConfig`), and this is the one
    place that specializes a planned job into a Wan2.2 command."""
    return build_training_command(job.job_id, **kwargs)


def write_job_inputs(job: JobRecord, command: TrainingCommand) -> None:
    """Writes the one input the entrypoint script needs that isn't
    already on disk: the job's `TrainingConfig`, serialized to the path
    `command.config_path` points at. The dataset manifest is expected to
    already exist at `command.dataset_manifest_path` (built ahead of
    time via `Wan22DatasetAdapter.write_manifest_jsonl` - that step
    needs a real dataset and stays a separate, explicit action)."""
    Path(command.config_path).parent.mkdir(parents=True, exist_ok=True)
    job.config.to_yaml(command.config_path)


def dispatch_via_kaggle(
    job: JobRecord,
    command: TrainingCommand,
    kaggle_client: KaggleClient,
    kernel_ref: KaggleKernelRef,
    *,
    git_ref: str = "master",
    dataset_owner_slug: str | None = None,
    extra_dataset_sources: tuple[KaggleDatasetRef, ...] = (),
) -> str:
    """Item 8 (Kaggle half): pushes a real, runnable Kaggle kernel via
    the real `KaggleClient` built in the automation layer.

    A plain Kaggle kernel push cannot receive CLI arguments the way a
    local subprocess or `TrainingCommand.to_argv()` assumes - `kaggle
    kernels push` runs `code_file` with no argv at all (see
    docs/adr/0025-kaggle-dispatch-argv-fix.md for how this was found and
    why it matters: the original ADR 0023 wiring pushed
    `wan22_lora_train.py` directly as `code_file`, which would have
    crashed on Kaggle's side on its first required `--config` argument).

    The real fix: upload `command.config_path` +
    `command.dataset_manifest_path` as a Kaggle dataset (mounted
    read-only under `/kaggle/input/<slug>/` at kernel runtime), and push
    `kaggle_kernel_runner.py` (which lives alongside the entrypoint, and
    reads its inputs from that mount, then calls
    `wan22_lora_train.main()` directly) as the kernel's `code_file`
    instead of the entrypoint itself. `kernel_dir` is still the
    entrypoint script's own directory - both files must be pushed
    together, since the runner imports the entrypoint by module name.

    `git_ref` is also written into that same uploaded dataset
    (`git_ref.txt`) - `kaggle_kernel_runner.py` clones this repo fresh
    inside the kernel (no persistent disk between runs) and needs to
    know which branch/tag/commit to check out; a plain `git clone` with
    no `--branch` would silently pull whatever the repo's *default*
    branch happens to be, which will not contain this code until this
    work is actually merged there. Callers dispatching from a feature
    branch (e.g. a CI job running via `${{ github.ref_name }}`) must
    pass that branch name here.
    """
    write_job_inputs(job, command)

    dataset_input_dir = Path(command.config_path).parent / "kaggle_dataset_input"
    dataset_input_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(command.config_path, dataset_input_dir / "config.yaml")
    shutil.copyfile(command.dataset_manifest_path, dataset_input_dir / "dataset_manifest.jsonl")
    (dataset_input_dir / "git_ref.txt").write_text(git_ref)

    input_dataset_ref = KaggleDatasetRef(
        owner_slug=dataset_owner_slug or kernel_ref.owner_slug,
        dataset_slug=f"{job.job_id}-input".replace("_", "-"),
    )
    kaggle_client.upload_dataset(
        dataset_input_dir,
        DatasetMetadata(
            dataset_ref=input_dataset_ref,
            title=f"Wan2.2 training input - {job.job_id}",
            subtitle="config.yaml + dataset_manifest.jsonl for one training run - see kaggle_kernel_runner.py",
        ),
        is_new=True,
    )

    entrypoint_path = Path(command.entrypoint)
    runner_path = entrypoint_path.parent / _KAGGLE_RUNNER_FILENAME
    push_config = KernelPushConfig(
        kernel_ref=kernel_ref,
        title=f"Sallehly Wan2.2 LoRA training - {job.job_id}",
        code_file=runner_path.name,
        dataset_sources=(input_dataset_ref, *extra_dataset_sources),
    )
    return kaggle_client.push_kernel(entrypoint_path.parent, push_config)


def dispatch_via_modal(
    job: JobRecord,
    command: TrainingCommand,
    modal_launcher: ModalJobLauncher,
    *,
    gpu_type: GPUType,
    function_name: str = "train_wan22_lora",
    function_timeout_sec: int,
    max_wall_clock_sec: int,
) -> ModalJobHandle:
    """Item 8 (Modal half): launches the entrypoint as a Modal function
    via the real `ModalJobLauncher`. `function_timeout_sec` documents
    what the entrypoint's own (currently nonexistent) `@app.function(...)`
    decorator would declare once this script is deployed as a real Modal
    app - see `ModalJobConfig`'s own docstring for why that can't be set
    from the CLI side."""
    write_job_inputs(job, command)
    modal_config = ModalJobConfig(
        app_entrypoint=command.entrypoint,
        function_name=function_name,
        gpu_type=gpu_type,
        function_timeout_sec=function_timeout_sec,
        max_wall_clock_sec=max_wall_clock_sec,
        extra_args=command.to_modal_extra_args(),
    )
    return modal_launcher.launch(modal_config)
