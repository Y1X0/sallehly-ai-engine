from __future__ import annotations

from dataclasses import dataclass, field

_DEFAULT_ENTRYPOINT = "services/training/entrypoints/wan22_lora_train.py"


@dataclass(frozen=True)
class TrainingCommand:
    """The single source of truth for "what command actually runs Wan2.2
    LoRA training" for one job. Built once (`build_training_command`),
    then handed to whichever launcher actually dispatches it - a local
    subprocess, a Kaggle kernel, or a Modal function - so Kaggle/Modal
    integration code never duplicates argument-building logic, and
    adding a fourth launcher later only means adding one more `to_*()`
    method here, not touching the launchers themselves."""

    entrypoint: str
    config_path: str
    dataset_manifest_path: str
    output_dir: str
    checkpoint_store_dir: str
    job_id: str
    extra_args: dict[str, str] = field(default_factory=dict)

    def to_argv(self, *, python: str = "python") -> list[str]:
        """The command a local subprocess (or a Kaggle kernel's own
        `code_file`, invoked the same way) would run."""
        args = [
            python,
            self.entrypoint,
            "--config", self.config_path,
            "--dataset-manifest", self.dataset_manifest_path,
            "--output-dir", self.output_dir,
            "--checkpoint-store-dir", self.checkpoint_store_dir,
            "--job-id", self.job_id,
        ]
        for key, value in self.extra_args.items():
            args.extend([f"--{key}", value])
        return args

    def to_modal_extra_args(self) -> dict[str, str]:
        """Modal auto-generates CLI flags from the target function's own
        parameters when invoked via `modal run entrypoint::fn --flag
        value` - this produces the same flag names `to_argv()` uses
        (minus the python interpreter / entrypoint path, which
        `ModalJobConfig.app_entrypoint`/`function_name` already carry)."""
        args = {
            "config": self.config_path,
            "dataset-manifest": self.dataset_manifest_path,
            "output-dir": self.output_dir,
            "checkpoint-store-dir": self.checkpoint_store_dir,
            "job-id": self.job_id,
        }
        args.update(self.extra_args)
        return args


def build_training_command(
    job_id: str,
    *,
    entrypoint: str = _DEFAULT_ENTRYPOINT,
    base_dir: str = ".training-automation/runs",
    extra_args: dict[str, str] | None = None,
) -> TrainingCommand:
    run_dir = f"{base_dir}/{job_id}"
    return TrainingCommand(
        entrypoint=entrypoint,
        config_path=f"{run_dir}/config.yaml",
        dataset_manifest_path=f"{run_dir}/dataset_manifest.jsonl",
        output_dir=f"{run_dir}/output",
        checkpoint_store_dir=f"{run_dir}/checkpoints",
        job_id=job_id,
        extra_args=dict(extra_args or {}),
    )
