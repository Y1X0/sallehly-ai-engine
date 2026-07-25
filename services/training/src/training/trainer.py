from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable

from .checkpoint import CheckpointRecord, ICheckpointStore
from .config import TrainingConfig


@dataclass
class TrainingRunResult:
    run_id: str
    status: str
    """"completed" or "failed" - deliberately not an Enum, mirroring
    GenerationJobStatus's string-value shape (services/render-orchestrator)
    so this serializes the same way every other status field in this
    codebase does."""
    final_step: int
    checkpoint_ids: list[str] = field(default_factory=list)
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "final_step": self.final_step,
            "checkpoint_ids": self.checkpoint_ids,
            "error_message": self.error_message,
        }


class ITrainer(ABC):
    """The training-execution contract - deliberately as small as
    `IVideoEngine`/`IComputeProvider` (packages/video-engine-sdk): one
    method, taking a fully-specified `TrainingConfig` and returning a
    `TrainingRunResult`. A future real trainer (calling into
    `accelerate`/`diffusers`/a custom training loop on real GPU hardware)
    implements this exact interface - nothing above it (a training CLI,
    a future orchestrator) needs to change when that lands, the same
    swap-point guarantee ADR 0001/0002 give the generation side."""

    @abstractmethod
    def train(self, config: TrainingConfig) -> TrainingRunResult: ...


class DryRunTrainer(ITrainer):
    """The only `ITrainer` implementation today - proves the training
    orchestration shape (step loop, periodic checkpointing, an eval-hook
    callback) is correct before any GPU-backed trainer exists to plug in
    behind it. Never reads dataset bytes, never imports torch, never
    downloads a model - it advances a step counter and writes a
    `CheckpointRecord` with a synthetically decreasing loss value every
    `checkpoint_every_steps`, the same "prove the pipeline without the
    expensive resource" pattern `LocalProvider` already established for
    compute jobs (services/video-engine-adapter/compute/local_provider.py).

    `on_step`, if given, is called with the current step number after
    each step - this is where Stage 7's eval-cadence hook
    (docs/adr/0021-phase9-preparation.md) attaches once a real
    `IBenchmarkRunner` exists; tests use it to assert the loop actually
    ran the expected number of times without needing real training.
    """

    def __init__(self, checkpoint_store: ICheckpointStore, on_step: Callable[[int], None] | None = None) -> None:
        self._checkpoints = checkpoint_store
        self._on_step = on_step

    def train(self, config: TrainingConfig) -> TrainingRunResult:
        config.validate()
        checkpoint_ids: list[str] = []
        step = 0
        try:
            while step < config.max_train_steps:
                step += 1
                if self._on_step is not None:
                    self._on_step(step)
                if step % config.checkpoint_every_steps == 0 or step == config.max_train_steps:
                    checkpoint_ids.append(self._checkpoint(config, step))
            return TrainingRunResult(run_id=config.run_id, status="completed", final_step=step, checkpoint_ids=checkpoint_ids)
        except Exception as exc:  # noqa: BLE001 - any failure mid-loop means the run failed, by design
            return TrainingRunResult(
                run_id=config.run_id,
                status="failed",
                final_step=step,
                checkpoint_ids=checkpoint_ids,
                error_message=str(exc),
            )

    def _checkpoint(self, config: TrainingConfig, step: int) -> str:
        # A monotonically decreasing synthetic loss - just enough shape
        # for RegressionDetector/benchmark tests to have real numbers to
        # compare, never a real training signal.
        synthetic_loss = max(0.01, 1.0 - (step / config.max_train_steps) * 0.9)
        checkpoint_id = f"ckpt_{config.run_id}_{step:06d}"
        self._checkpoints.save(
            CheckpointRecord(
                checkpoint_id=checkpoint_id,
                run_id=config.run_id,
                step=step,
                artifact_uri=f"dryrun://{config.run_id}/{checkpoint_id}",
                size_bytes=0,
                metrics={"loss": round(synthetic_loss, 4)},
            )
        )
        return checkpoint_id
