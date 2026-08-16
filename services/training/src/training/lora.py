from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LoRAConfig:
    """Parameter-efficient fine-tuning configuration - Phase 9's default
    fine-tuning strategy (see docs/adr/0021-phase9-preparation.md, Stage
    5/6 of the roadmap): orders of magnitude cheaper to iterate than a
    full fine-tune, and a bad adapter is cheap to discard. This is a
    pure schema/validation object - it describes *what a training run
    should configure*, not a live PEFT/diffusers integration, since no
    GPU or base model exists in this environment to attach one to yet.
    """

    rank: int = 16
    alpha: int = 32
    target_modules: tuple[str, ...] = ("to_q", "to_k", "to_v", "to_out.0")
    dropout: float = 0.0

    def validate(self) -> None:
        if self.rank <= 0:
            raise ValueError(f"LoRAConfig.rank must be positive, got {self.rank}")
        if self.alpha <= 0:
            raise ValueError(f"LoRAConfig.alpha must be positive, got {self.alpha}")
        if not self.target_modules:
            raise ValueError("LoRAConfig.target_modules must not be empty")
        if not (0.0 <= self.dropout < 1.0):
            raise ValueError(f"LoRAConfig.dropout must be in [0.0, 1.0), got {self.dropout}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "alpha": self.alpha,
            "target_modules": list(self.target_modules),
            "dropout": self.dropout,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LoRAConfig":
        return cls(
            rank=data["rank"],
            alpha=data["alpha"],
            target_modules=tuple(data["target_modules"]),
            dropout=data.get("dropout", 0.0),
        )


@dataclass(frozen=True)
class LoRAMergePlan:
    """Describes how one or more trained LoRA adapters would be combined
    into a single deployable checkpoint - a deliberate, explicit
    promotion step (docs/adr/0021-phase9-preparation.md), never an
    automatic side effect of training. `weights` lets multiple
    style/brand adapters (Stage 6 of the Phase 9 roadmap) be blended
    rather than only ever merging one at a time."""

    adapter_checkpoint_ids: tuple[str, ...]
    weights: tuple[float, ...]
    target_checkpoint_id: str

    def validate(self) -> None:
        if not self.adapter_checkpoint_ids:
            raise ValueError("LoRAMergePlan.adapter_checkpoint_ids must not be empty")
        if len(self.adapter_checkpoint_ids) != len(self.weights):
            raise ValueError(
                "LoRAMergePlan.weights must have the same length as adapter_checkpoint_ids "
                f"({len(self.adapter_checkpoint_ids)} vs {len(self.weights)})"
            )
        if any(w < 0 for w in self.weights):
            raise ValueError("LoRAMergePlan.weights must all be non-negative")
        if not self.target_checkpoint_id:
            raise ValueError("LoRAMergePlan.target_checkpoint_id must not be empty")
