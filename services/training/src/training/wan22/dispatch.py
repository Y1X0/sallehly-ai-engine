from __future__ import annotations

from pathlib import Path

from ..automation.controller import JobRecord
from ..automation.kaggle_client import KaggleClient, KaggleDatasetRef, KaggleKernelRef, KernelPushConfig
from ..automation.modal_client import GPUType, ModalJobConfig, ModalJobHandle, ModalJobLauncher
from .command import TrainingCommand, build_training_command


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
    dataset_sources: tuple[KaggleDatasetRef, ...] = (),
) -> str:
    """Item 8 (Kaggle half): pushes the entrypoint script as a Kaggle
    kernel via the real `KaggleClient` built in the automation layer -
    no new Kaggle integration code, just wiring. `kernel_dir` is the
    entrypoint script's own directory, since `kaggle kernels push`
    uploads a whole directory and `code_file` must live inside it."""
    write_job_inputs(job, command)
    entrypoint_path = Path(command.entrypoint)
    push_config = KernelPushConfig(
        kernel_ref=kernel_ref,
        title=f"Sallehly Wan2.2 LoRA training - {job.job_id}",
        code_file=entrypoint_path.name,
        dataset_sources=dataset_sources,
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
