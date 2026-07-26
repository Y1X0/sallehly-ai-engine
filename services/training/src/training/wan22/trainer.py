from __future__ import annotations

from pathlib import Path
from typing import Callable

from ..config import TrainingConfig
from ..trainer import ITrainer, TrainingRunResult
from .backend import IWan22TrainingBackend
from .checkpoint_writer import Wan22CheckpointWriter
from .dataset_adapter import Wan22ManifestEntry
from .lora_config import Wan22LoRAConfig


class Wan22LoRATrainer(ITrainer):
    """`ITrainer` for Wan2.2 LoRA fine-tuning - same step/checkpoint loop
    shape `DryRunTrainer` proved out in Phase 9 Preparation, specialized
    to Wan2.2's requirement that every configured expert (one for
    TI2V-5B, two for the A14B MoE variants) trains and checkpoints
    together at every step, never separately. Dataset batches are drawn
    round-robin from a pre-built `Wan22ManifestEntry` list (from
    `Wan22DatasetAdapter`); the actual gradient computation happens
    inside `backend.train_step()`, which - with the only backend that
    exists today (`UnavailableWan22Backend`) - always raises
    `ModelUnavailableError` on the very first call. That failure is
    caught by this trainer's own try/except (same contract
    `DryRunTrainer` already established) and reported as a normal
    `TrainingRunResult(status="failed", ...)`, not a crash - proving
    this orchestration is genuinely wired end-to-end while guaranteeing
    it cannot run real training without a real backend attached.
    """

    def __init__(
        self,
        *,
        backend: IWan22TrainingBackend,
        checkpoint_writer: Wan22CheckpointWriter,
        dataset_entries: list[Wan22ManifestEntry],
        lora_config: Wan22LoRAConfig,
        output_dir: str | Path,
        on_step: Callable[[int], None] | None = None,
        on_checkpoint: Callable[[int, list[str]], None] | None = None,
    ) -> None:
        self._backend = backend
        self._checkpoints = checkpoint_writer
        self._dataset_entries = dataset_entries
        self._lora_config = lora_config
        self._output_dir = Path(output_dir)
        self._on_step = on_step
        self._on_checkpoint = on_checkpoint

    def train(self, config: TrainingConfig) -> TrainingRunResult:
        config.validate()
        self._lora_config.validate()
        if config.base_model_id != self._lora_config.base_model_id:
            raise ValueError(
                f"TrainingConfig.base_model_id ({config.base_model_id!r}) does not match "
                f"Wan22LoRAConfig.base_model_id ({self._lora_config.base_model_id!r})"
            )
        if not self._dataset_entries:
            raise ValueError("Wan22LoRATrainer has no dataset entries to train on")

        checkpoint_ids: list[str] = []
        step = 0
        try:
            while step < config.max_train_steps:
                step += 1
                batch = self._dataset_entries[(step - 1) % len(self._dataset_entries)]

                for expert, lora in self._lora_config.experts.items():
                    self._backend.train_step(expert=expert, step=step, batch=batch, lora_config=lora)

                if self._on_step is not None:
                    self._on_step(step)

                if step % config.checkpoint_every_steps == 0 or step == config.max_train_steps:
                    step_checkpoint_ids = self._checkpoint_all_experts(config, step)
                    checkpoint_ids.extend(step_checkpoint_ids)
                    if self._on_checkpoint is not None:
                        self._on_checkpoint(step, step_checkpoint_ids)

            return TrainingRunResult(
                run_id=config.run_id, status="completed", final_step=step, checkpoint_ids=checkpoint_ids
            )
        except Exception as exc:  # noqa: BLE001 - any failure mid-loop means the run failed, by design
            return TrainingRunResult(
                run_id=config.run_id,
                status="failed",
                final_step=step,
                checkpoint_ids=checkpoint_ids,
                error_message=str(exc),
            )

    def _checkpoint_all_experts(self, config: TrainingConfig, step: int) -> list[str]:
        checkpoint_ids = []
        for expert in self._lora_config.experts:
            artifact_uri = self._backend.save_checkpoint(expert=expert, step=step, output_dir=self._output_dir)
            checkpoint_ids.append(
                self._checkpoints.save_expert_checkpoint(
                    run_id=config.run_id, step=step, expert=expert, artifact_uri=artifact_uri,
                )
            )
        # Real integrity check, not just documentation: this raises
        # PairedCheckpointMissingError if the loop above somehow saved
        # fewer experts than configured before returning successfully.
        self._checkpoints.get_paired_checkpoints(config.run_id, step, frozenset(self._lora_config.experts))
        return checkpoint_ids
