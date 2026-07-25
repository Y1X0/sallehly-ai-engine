from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .lora import LoRAConfig

_VALID_STRATEGIES = frozenset({"lora", "full_finetune"})
_VALID_PRECISIONS = frozenset({"bf16", "fp16", "no"})


@dataclass(frozen=True)
class BaseModelInfo:
    """Real, citable facts about a candidate open-weight base model
    (Phase 9 roadmap Stage 0 - base model selection,
    docs/adr/0021-phase9-preparation.md). Deliberately just metadata -
    no weights, no download, no code that touches a GPU. `license_notes`
    exists because licenses differ by *variant* (e.g. CogVideoX-2B vs
    -5B) and by *scale* (e.g. HunyuanVideo's >100M-MAU carve-out) in ways
    a single `license` string can't capture honestly - always re-verify
    against the model's current license text before training, since
    these terms can change after this was written."""

    model_id: str
    display_name: str
    publisher: str
    license: str
    license_notes: str
    default_resolution: str
    default_fps: int
    min_vram_gb: float
    commercial_use_verified: bool
    source_url: str


BASE_MODEL_REGISTRY: dict[str, BaseModelInfo] = {
    "wan2.1": BaseModelInfo(
        model_id="wan2.1",
        display_name="Wan2.1",
        publisher="Alibaba",
        license="Apache-2.0",
        license_notes=(
            "Fully permissive open-source license - no revenue cap, no output-usage "
            "restriction. Matches the license already recorded on Wan21Adapter's "
            "CapabilityManifest (services/video-engine-adapter)."
        ),
        default_resolution="1280x720",
        default_fps=24,
        min_vram_gb=24.0,
        commercial_use_verified=True,
        source_url="https://github.com/Wan-Video/Wan2.1",
    ),
    "hunyuanvideo": BaseModelInfo(
        model_id="hunyuanvideo",
        display_name="HunyuanVideo",
        publisher="Tencent",
        license="Tencent Hunyuan Community License",
        license_notes=(
            "Commercial use is permitted, but the license does NOT apply in the EU, "
            "UK, or South Korea, and any product with >100M monthly active users needs "
            "a separate license granted at Tencent's discretion. Outputs may not be "
            "used to train a competing model. Verify current license text before "
            "training - checked via web search 2026-07-25, not independently executed "
            "in this sandbox."
        ),
        default_resolution="1280x720",
        default_fps=24,
        min_vram_gb=60.0,
        commercial_use_verified=True,
        source_url="https://github.com/Tencent-Hunyuan/HunyuanVideo",
    ),
    "cogvideox": BaseModelInfo(
        model_id="cogvideox",
        display_name="CogVideoX",
        publisher="Zhipu AI (Z.ai)",
        license="Apache-2.0 (CogVideoX-2B only) / custom CogVideoX LICENSE (CogVideoX-5B)",
        license_notes=(
            "Only the 2B variant is Apache-2.0 and unambiguously commercial-friendly. "
            "The 5B variant (better quality, the one likely worth fine-tuning) ships "
            "under a separate custom license that must be reviewed independently before "
            "any commercial training run - do not assume Apache-2.0 terms extend to it."
        ),
        default_resolution="720x480",
        default_fps=8,
        min_vram_gb=18.0,
        commercial_use_verified=False,
        source_url="https://github.com/zai-org/CogVideo",
    ),
    "stable-video-diffusion": BaseModelInfo(
        model_id="stable-video-diffusion",
        display_name="Stable Video Diffusion",
        publisher="Stability AI",
        license="Stability AI Community License",
        license_notes=(
            "Free for research, non-commercial, and commercial use by organizations "
            "under $1M annual revenue; organizations above that threshold need a "
            "separate Stability AI enterprise license. Requires attribution "
            "('Powered by Stability AI') in any distributed product. This project's "
            "revenue status must be checked against the $1M threshold before training, "
            "not assumed."
        ),
        default_resolution="1024x576",
        default_fps=25,
        min_vram_gb=20.0,
        commercial_use_verified=False,
        source_url="https://huggingface.co/stabilityai/stable-video-diffusion-img2vid-xt-1-1",
    ),
}


@dataclass(frozen=True)
class TrainingConfig:
    """The full description of one training run - fine-tune or LoRA -
    against one of `BASE_MODEL_REGISTRY`'s candidate base models. This is
    pure configuration: constructing, validating, and round-tripping one
    to/from YAML never touches a GPU, downloads a model, or runs
    training - see `ITrainer` (trainer.py) for where the actual
    (currently dry-run-only) execution boundary sits.
    """

    schema_version: str
    run_id: str
    base_model_id: str
    base_model_revision: str
    strategy: str
    dataset_version: str
    resolution: str
    fps: int
    max_frames: int
    learning_rate: float
    batch_size: int
    gradient_accumulation_steps: int
    max_train_steps: int
    mixed_precision: str
    min_vram_gb: float
    gpu_count: int
    checkpoint_every_steps: int
    eval_every_steps: int
    seed: int
    lora: LoRAConfig | None = None
    notes: str = ""

    def validate(self) -> None:
        if not self.run_id:
            raise ValueError("TrainingConfig.run_id must not be empty")
        if self.strategy not in _VALID_STRATEGIES:
            raise ValueError(
                f"TrainingConfig.strategy must be one of {sorted(_VALID_STRATEGIES)}, got {self.strategy!r}"
            )
        if self.strategy == "lora" and self.lora is None:
            raise ValueError("TrainingConfig.lora is required when strategy='lora'")
        if self.lora is not None:
            self.lora.validate()
        if "x" not in self.resolution.lower():
            raise ValueError(f"TrainingConfig.resolution must be 'WIDTHxHEIGHT', got {self.resolution!r}")
        width_str, _, height_str = self.resolution.lower().partition("x")
        if not (width_str.isdigit() and height_str.isdigit()):
            raise ValueError(f"TrainingConfig.resolution must be 'WIDTHxHEIGHT' of integers, got {self.resolution!r}")
        if self.fps <= 0:
            raise ValueError(f"TrainingConfig.fps must be positive, got {self.fps}")
        if self.max_frames <= 0:
            raise ValueError(f"TrainingConfig.max_frames must be positive, got {self.max_frames}")
        if self.learning_rate <= 0:
            raise ValueError(f"TrainingConfig.learning_rate must be positive, got {self.learning_rate}")
        if self.batch_size < 1:
            raise ValueError(f"TrainingConfig.batch_size must be >= 1, got {self.batch_size}")
        if self.gradient_accumulation_steps < 1:
            raise ValueError(
                f"TrainingConfig.gradient_accumulation_steps must be >= 1, got {self.gradient_accumulation_steps}"
            )
        if self.max_train_steps < 1:
            raise ValueError(f"TrainingConfig.max_train_steps must be >= 1, got {self.max_train_steps}")
        if self.mixed_precision not in _VALID_PRECISIONS:
            raise ValueError(
                f"TrainingConfig.mixed_precision must be one of {sorted(_VALID_PRECISIONS)}, got {self.mixed_precision!r}"
            )
        if self.min_vram_gb <= 0:
            raise ValueError(f"TrainingConfig.min_vram_gb must be positive, got {self.min_vram_gb}")
        if self.gpu_count < 1:
            raise ValueError(f"TrainingConfig.gpu_count must be >= 1, got {self.gpu_count}")
        if self.checkpoint_every_steps < 1:
            raise ValueError(f"TrainingConfig.checkpoint_every_steps must be >= 1, got {self.checkpoint_every_steps}")
        if self.eval_every_steps < 1:
            raise ValueError(f"TrainingConfig.eval_every_steps must be >= 1, got {self.eval_every_steps}")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["lora"] = self.lora.to_dict() if self.lora is not None else None
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TrainingConfig":
        lora_data = data.get("lora")
        return cls(
            schema_version=data["schema_version"],
            run_id=data["run_id"],
            base_model_id=data["base_model_id"],
            base_model_revision=data["base_model_revision"],
            strategy=data["strategy"],
            dataset_version=data["dataset_version"],
            resolution=data["resolution"],
            fps=data["fps"],
            max_frames=data["max_frames"],
            learning_rate=data["learning_rate"],
            batch_size=data["batch_size"],
            gradient_accumulation_steps=data["gradient_accumulation_steps"],
            max_train_steps=data["max_train_steps"],
            mixed_precision=data["mixed_precision"],
            min_vram_gb=data["min_vram_gb"],
            gpu_count=data["gpu_count"],
            checkpoint_every_steps=data["checkpoint_every_steps"],
            eval_every_steps=data["eval_every_steps"],
            seed=data["seed"],
            lora=LoRAConfig.from_dict(lora_data) if lora_data is not None else None,
            notes=data.get("notes", ""),
        )

    def to_yaml(self, path: str | Path) -> None:
        Path(path).write_text(yaml.safe_dump(self.to_dict(), sort_keys=False))

    @classmethod
    def from_yaml(cls, path: str | Path) -> "TrainingConfig":
        data = yaml.safe_load(Path(path).read_text())
        return cls.from_dict(data)
