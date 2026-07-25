from __future__ import annotations

from typing import Any

import schemas
from cinematic_intelligence_sdk import IRepairStrategy, QualityIssue, QualityReport, QualityScores
from config_sdk import REPAIR_STRATEGY_REGISTRY

from .strategies import (
    CameraRepairStrategy,
    IdentityRepairStrategy,
    LightingRepairStrategy,
    PromptRepairStrategy,
    StyleRepairStrategy,
)

_BUILTIN_STRATEGIES = (
    PromptRepairStrategy,
    CameraRepairStrategy,
    StyleRepairStrategy,
    IdentityRepairStrategy,
    LightingRepairStrategy,
)

# Which QualityReport.scores dimension routes to which repair_type when it
# is the worst-scoring one. composition_quality/prompt_adherence both
# route to prompt_repair (a clearer/stronger prompt is the fix for both);
# motion_quality routes to camera_repair (motion is a camera-continuity
# concern in this schema's vocabulary).
_METRIC_TO_REPAIR_TYPE: dict[str, str] = {
    "identity_consistency": "identity_repair",
    "camera_consistency": "camera_repair",
    "motion_quality": "camera_repair",
    "lighting_consistency": "lighting_repair",
    "style_consistency": "style_repair",
    "composition_quality": "prompt_repair",
    "prompt_adherence": "prompt_repair",
}


def register_defaults() -> None:
    """Registers every built-in IRepairStrategy into
    REPAIR_STRATEGY_REGISTRY, keyed by repair_type. Idempotent."""
    for strategy_cls in _BUILTIN_STRATEGIES:
        REPAIR_STRATEGY_REGISTRY.register_if_absent(strategy_cls.repair_type, strategy_cls)


class AutomaticRepairEngineError(Exception):
    """Raised when a QualityReport dict is missing required fields, or an
    assembled RepairAction fails schema validation."""


class AutomaticRepairEngine:
    """Given a QualityReport that recommends a repair, picks the
    worst-scoring dimension, routes it to the matching IRepairStrategy
    via REPAIR_STRATEGY_REGISTRY, and returns the resulting RepairAction
    - always scoped to exactly the one shot_id the QualityReport is
    about. Never regenerates or touches any other shot in the project.
    Requires `register_defaults()` to have been called first."""

    def repair(self, quality_report: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        repair_type = self._pick_repair_type(quality_report)
        strategy: IRepairStrategy = REPAIR_STRATEGY_REGISTRY.create(repair_type)
        action = strategy.repair(quality_report_from_dict(quality_report), context or {})
        action_dict = repair_action_to_dict(action)
        try:
            schemas.validate(action_dict, "repair_action")
        except Exception as exc:  # noqa: BLE001
            raise AutomaticRepairEngineError(f"Assembled RepairAction failed validation: {exc}") from exc
        return action_dict

    def _pick_repair_type(self, quality_report: dict[str, Any]) -> str:
        scores = quality_report["scores"]
        candidates = {k: v for k, v in scores.items() if k in _METRIC_TO_REPAIR_TYPE}
        worst_metric = min(candidates, key=lambda k: candidates[k])
        return _METRIC_TO_REPAIR_TYPE[worst_metric]


def quality_report_from_dict(d: dict[str, Any]) -> QualityReport:
    scores = d["scores"]
    return QualityReport(
        schema_version=d["schema_version"],
        report_id=d["report_id"],
        project_id=d["project_id"],
        shot_id=d["shot_id"],
        scores=QualityScores(**scores),
        issues=tuple(QualityIssue(**issue) for issue in d.get("issues", [])),
        repair_recommended=d.get("repair_recommended", False),
        embeddings_used=d.get("embeddings_used", False),
        generated_at=d.get("generated_at"),
    )


def repair_action_to_dict(action: Any) -> dict[str, Any]:
    d: dict[str, Any] = {
        "schema_version": action.schema_version,
        "repair_id": action.repair_id,
        "project_id": action.project_id,
        "shot_id": action.shot_id,
        "quality_report_id": action.quality_report_id,
        "repair_type": action.repair_type,
        "strategy_id": action.strategy_id,
        "status": action.status,
    }
    if action.description:
        d["description"] = action.description
    if action.before_summary:
        d["before_summary"] = action.before_summary
    if action.after_summary:
        d["after_summary"] = action.after_summary
    if action.applied_at:
        d["applied_at"] = action.applied_at
    return d


__all__ = [
    "AutomaticRepairEngine",
    "AutomaticRepairEngineError",
    "CameraRepairStrategy",
    "IdentityRepairStrategy",
    "LightingRepairStrategy",
    "PromptRepairStrategy",
    "StyleRepairStrategy",
    "quality_report_from_dict",
    "register_defaults",
    "repair_action_to_dict",
]
