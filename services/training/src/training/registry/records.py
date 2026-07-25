from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from video_engine_sdk import CapabilityManifest


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PromotionStatus(str, Enum):
    """A model version's place in the promotion pipeline (Phase 9
    roadmap Stage 9/10, docs/adr/0021-phase9-preparation.md) - mirrors
    `ProjectStatus`'s string-`Enum` shape (packages/persistence) so it
    serializes and compares the same way every other status field in
    this codebase does.

    STAGING -> CANARY -> PRODUCTION is the forward promotion path;
    REJECTED is a terminal state for a version that failed the Stage 8
    benchmarking gate; ARCHIVED is where a version goes once a newer one
    supersedes it in PRODUCTION - kept, not deleted, so `rollback()` has
    something to roll back to.
    """

    STAGING = "staging"
    CANARY = "canary"
    PRODUCTION = "production"
    ARCHIVED = "archived"
    REJECTED = "rejected"


_FORWARD_TRANSITIONS: dict[PromotionStatus, frozenset[PromotionStatus]] = {
    PromotionStatus.STAGING: frozenset({PromotionStatus.CANARY, PromotionStatus.REJECTED}),
    PromotionStatus.CANARY: frozenset({PromotionStatus.PRODUCTION, PromotionStatus.STAGING, PromotionStatus.REJECTED}),
    PromotionStatus.PRODUCTION: frozenset({PromotionStatus.ARCHIVED}),
    PromotionStatus.ARCHIVED: frozenset({PromotionStatus.CANARY}),
    PromotionStatus.REJECTED: frozenset(),
}


class InvalidPromotionTransitionError(Exception):
    """Raised when a promotion would skip the canary stage (e.g. staging
    straight to production) or move a terminal REJECTED version anywhere
    - the same "the state machine itself refuses invalid moves" pattern
    `ProjectLifecycle` uses for `ProjectStatus`, not left to the caller
    to remember."""


def assert_valid_transition(current: PromotionStatus, target: PromotionStatus) -> None:
    if target not in _FORWARD_TRANSITIONS.get(current, frozenset()):
        raise InvalidPromotionTransitionError(
            f"Cannot promote a version from {current.value!r} to {target.value!r} - "
            f"valid next states from {current.value!r} are "
            f"{sorted(s.value for s in _FORWARD_TRANSITIONS.get(current, frozenset()))}"
        )


@dataclass
class ModelVersionRecord:
    """One promotable entry in the Model Registry - typically pointing
    at exactly one `checkpoint.CheckpointRecord` (the checkpoint someone
    decided was worth evaluating), plus everything a promotion decision
    needs: which dataset trained it, what its capability envelope is,
    and what it scored on the Stage 7/8 evaluation harness.
    `capability_manifest` is a real `video_engine_sdk.CapabilityManifest`
    - the exact same type `IVideoEngine.capabilities()` returns - so a
    promoted version's declared envelope can be validated against real
    `IVideoEngine` expectations before it's ever wired into a
    `SallehlyModelAdapter` (see `registry.compatibility`).
    """

    version_id: str
    base_model_id: str
    checkpoint_id: str
    training_run_id: str
    dataset_version: str
    capability_manifest: CapabilityManifest
    lora_config: dict[str, Any] | None = None
    eval_scores: dict[str, float] = field(default_factory=dict)
    status: PromotionStatus = PromotionStatus.STAGING
    notes: str = ""
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        manifest = self.capability_manifest
        return {
            "version_id": self.version_id,
            "base_model_id": self.base_model_id,
            "checkpoint_id": self.checkpoint_id,
            "training_run_id": self.training_run_id,
            "dataset_version": self.dataset_version,
            "capability_manifest": {
                "engine_id": manifest.engine_id,
                "engine_version": manifest.engine_version,
                "modes": manifest.modes,
                "max_shot_duration_sec": manifest.max_shot_duration_sec,
                "min_shot_duration_sec": manifest.min_shot_duration_sec,
                "resolutions": manifest.resolutions,
                "fps_options": manifest.fps_options,
                "motion_strength_range": list(manifest.motion_strength_range),
                "supports_negative_prompt": manifest.supports_negative_prompt,
                "supports_seed": manifest.supports_seed,
                "supports_conditioning_images": manifest.supports_conditioning_images,
                "max_conditioning_images": manifest.max_conditioning_images,
                "license": manifest.license,
                "min_vram_gb": manifest.min_vram_gb,
            },
            "lora_config": self.lora_config,
            "eval_scores": self.eval_scores,
            "status": self.status.value,
            "notes": self.notes,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModelVersionRecord":
        manifest_data = dict(data["capability_manifest"])
        manifest_data["motion_strength_range"] = tuple(manifest_data["motion_strength_range"])
        return cls(
            version_id=data["version_id"],
            base_model_id=data["base_model_id"],
            checkpoint_id=data["checkpoint_id"],
            training_run_id=data["training_run_id"],
            dataset_version=data["dataset_version"],
            capability_manifest=CapabilityManifest(**manifest_data),
            lora_config=data.get("lora_config"),
            eval_scores=dict(data.get("eval_scores") or {}),
            status=PromotionStatus(data["status"]),
            notes=data.get("notes", ""),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
        )
