from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..errors import ModelUnavailableError
from ..lora import LoRAConfig
from .dataset_adapter import Wan22ManifestEntry


@dataclass(frozen=True)
class TrainStepResult:
    loss: float
    metrics: dict[str, float] = field(default_factory=dict)


class IWan22TrainingBackend(ABC):
    """The one real execution boundary in this entire layer: everything
    above this interface (the dataset adapter, LoRA config, checkpoint
    writer, evaluation hooks, `Wan22LoRATrainer`'s step/checkpoint loop)
    is real, tested, CPU-only Python. What a `train_step()` call
    actually *does* - load Wan2.2 weights, run a forward/backward pass
    on real GPU hardware via `diffusers`/`musubi-tuner` - is deliberately
    not implemented here. A future real backend implements this exact
    interface (same swap-point discipline as `ITrainer`/`IVideoEngine`/
    `IComputeProvider` elsewhere in this codebase); nothing above it
    needs to change when that lands."""

    @abstractmethod
    def train_step(
        self, *, expert: str, step: int, batch: Wan22ManifestEntry, lora_config: LoRAConfig
    ) -> TrainStepResult: ...

    @abstractmethod
    def save_checkpoint(self, *, expert: str, step: int, output_dir: Path) -> str:
        """Returns the artifact_uri the saved weights would live at."""
        ...


class UnavailableWan22Backend(IWan22TrainingBackend):
    """The only `IWan22TrainingBackend` implementation that exists today.
    Raises `ModelUnavailableError` on the very first real call, always -
    there is no GPU, no downloaded Wan2.2 weights, and no diffusers/
    musubi-tuner integration in this environment. This is not a
    placeholder that happens to be unfinished; it is the deliberately
    correct behavior for "ready for the first GPU experiment, not
    executing one": `Wan22LoRATrainer.train()` calling into this backend
    fails cleanly and immediately, exactly like `BenchmarkRunner`
    pointed at the untrained `SallehlyModelAdapter` already does, rather
    than crashing or silently pretending to succeed.
    """

    def train_step(self, **_kwargs: Any) -> TrainStepResult:
        raise ModelUnavailableError(
            "Wan2.2 training backend unavailable: no GPU, no downloaded Wan2.2 weights, "
            "and no diffusers/musubi-tuner integration exists in this environment - see "
            "docs/adr/0023-wan22-training-execution-layer.md"
        )

    def save_checkpoint(self, **_kwargs: Any) -> str:
        raise ModelUnavailableError(
            "Wan2.2 training backend unavailable: cannot save a checkpoint with no real "
            "training backend attached - see docs/adr/0023-wan22-training-execution-layer.md"
        )
