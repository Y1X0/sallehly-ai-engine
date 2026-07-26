from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ..config import TrainingConfig
from ..lora import LoRAConfig

EXPERT_HIGH_NOISE = "high_noise"
EXPERT_LOW_NOISE = "low_noise"
EXPERT_UNIFIED = "unified"

_A14B_MODEL_IDS = frozenset({"wan2.2-t2v-a14b", "wan2.2-i2v-a14b"})
_UNIFIED_MODEL_IDS = frozenset({"wan2.2-ti2v-5b"})
_KNOWN_WAN22_MODEL_IDS = _A14B_MODEL_IDS | _UNIFIED_MODEL_IDS


def expected_experts(base_model_id: str) -> frozenset[str]:
    """Which expert names a Wan2.2 variant requires, structurally. A14B
    variants are a two-expert MoE DiT (separate high-noise/low-noise
    denoising networks switched by a fixed SNR/timestep threshold, not a
    learned router - see the Wan2.2 fine-tuning blueprint); TI2V-5B is a
    single unified network. Encoding this as a lookup (not a boolean
    flag) means adding a future Wan2.2 variant only requires one new
    entry here, not touching every call site that currently assumes
    "0 or 2 experts"."""
    if base_model_id in _A14B_MODEL_IDS:
        return frozenset({EXPERT_HIGH_NOISE, EXPERT_LOW_NOISE})
    if base_model_id in _UNIFIED_MODEL_IDS:
        return frozenset({EXPERT_UNIFIED})
    raise ValueError(
        f"Unknown Wan2.2 base_model_id: {base_model_id!r} - expected one of "
        f"{sorted(_KNOWN_WAN22_MODEL_IDS)}"
    )


@dataclass(frozen=True)
class Wan22LoRAConfig:
    """LoRA configuration for one Wan2.2 training run, keyed by expert
    name. The structural invariant this type exists to enforce: for an
    A14B model, `experts` can only ever be validly constructed with
    *both* `high_noise` and `low_noise` present - there is no way to
    build a `Wan22LoRAConfig` that fine-tunes only one A14B expert and
    have it pass `validate()`. This is the fine-tuning blueprint's
    "both experts must train together" requirement enforced as a type,
    not just documented as a risk."""

    base_model_id: str
    experts: dict[str, LoRAConfig]

    def validate(self) -> None:
        expected = expected_experts(self.base_model_id)
        actual = frozenset(self.experts)
        if actual != expected:
            raise ValueError(
                f"Wan22LoRAConfig for {self.base_model_id!r} must configure exactly "
                f"the experts {sorted(expected)}, got {sorted(actual)}"
            )
        for lora in self.experts.values():
            lora.validate()

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_model_id": self.base_model_id,
            "experts": {name: lora.to_dict() for name, lora in self.experts.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Wan22LoRAConfig":
        return cls(
            base_model_id=data["base_model_id"],
            experts={name: LoRAConfig.from_dict(lora) for name, lora in data["experts"].items()},
        )

    def to_yaml(self, path: str | Path) -> None:
        Path(path).write_text(yaml.safe_dump(self.to_dict(), sort_keys=False))

    @classmethod
    def from_yaml(cls, path: str | Path) -> "Wan22LoRAConfig":
        data = yaml.safe_load(Path(path).read_text())
        return cls.from_dict(data)

    @classmethod
    def from_training_config(
        cls,
        config: TrainingConfig,
        *,
        low_noise_lora: LoRAConfig | None = None,
    ) -> "Wan22LoRAConfig":
        """Expands `TrainingConfig.lora` (a single `LoRAConfig`, the
        schema every other base model already uses) into the per-expert
        shape a Wan2.2 A14B run needs. By default both experts share
        identical rank/alpha/target_modules/dropout - the fine-tuning
        blueprint's recommended starting point - but `low_noise_lora`
        lets the two experts be configured asymmetrically (e.g. a lower
        rank on one) once real training results justify it. For
        TI2V-5B, `low_noise_lora` is rejected: a unified model has only
        one expert to configure."""
        if config.lora is None:
            raise ValueError("TrainingConfig.lora is required to build a Wan22LoRAConfig")
        experts_needed = expected_experts(config.base_model_id)

        if experts_needed == frozenset({EXPERT_UNIFIED}):
            if low_noise_lora is not None:
                raise ValueError(
                    f"{config.base_model_id!r} is a unified (non-MoE) Wan2.2 variant - "
                    "low_noise_lora is only meaningful for the A14B MoE variants"
                )
            experts = {EXPERT_UNIFIED: config.lora}
        else:
            experts = {
                EXPERT_HIGH_NOISE: config.lora,
                EXPERT_LOW_NOISE: low_noise_lora or config.lora,
            }

        result = cls(base_model_id=config.base_model_id, experts=experts)
        result.validate()
        return result
