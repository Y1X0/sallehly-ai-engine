from __future__ import annotations

from typing import Any

import schemas
from cinematic_intelligence_sdk import IQualityMetric
from config_sdk import QUALITY_METRIC_REGISTRY

from ._util import new_id, now_iso

_SEVERITY_PENALTY = {"critical": 0.4, "warning": 0.15, "info": 0.05}

_CATEGORY_FOR_VIOLATION: dict[str, str] = {
    "character_identity_drift": "identity",
    "actor_position_jump": "identity",
    "eye_line_mismatch": "identity",
    "entry_exit_mismatch": "composition",
    "timing_gap": "composition",
    "object_location_conflict": "composition",
    "shot_rhythm_break": "composition",
    "motion_direction_flip": "motion",
    "camera_direction_flip": "camera",
    "impossible_camera_jump": "camera",
    "focal_length_jump": "camera",
    "camera_height_jump": "camera",
    "environment_jump": "lighting",
    "lighting_discontinuity": "lighting",
    "style_drift": "style",
}

_DEFAULT_REPAIR_THRESHOLD = 0.7


def _penalty_score(violations: list[dict[str, Any]], relevant_types: set[str] | None = None) -> float:
    score = 1.0
    for violation in violations:
        if relevant_types is not None and violation.get("violation_type") not in relevant_types:
            continue
        score -= _SEVERITY_PENALTY.get(violation.get("severity"), 0.1)
    return round(max(0.0, min(1.0, score)), 4)


class IdentityConsistencyMetric(IQualityMetric):
    """Penalizes scene-continuity violations that indicate a character's
    identity or blocking drifted between shots."""

    metric_id = "identity_consistency"
    _RELEVANT = {"character_identity_drift", "actor_position_jump", "eye_line_mismatch"}

    def score(self, shot_id: str, context: dict[str, Any]) -> float:
        return _penalty_score(context.get("scene_violations", []), self._RELEVANT)


class CameraConsistencyMetric(IQualityMetric):
    """Penalizes every camera-continuity violation - all of
    CameraContinuityEngine's violation types are camera-relevant by
    construction."""

    metric_id = "camera_consistency"

    def score(self, shot_id: str, context: dict[str, Any]) -> float:
        return _penalty_score(context.get("camera_violations", []))


class LightingConsistencyMetric(IQualityMetric):
    """Penalizes environment/lighting discontinuities - there is no
    dedicated lighting-continuity engine in Phase 7, so this reads the
    same scene_violations the Environment Consistency Engine's drift
    checks feed into."""

    metric_id = "lighting_consistency"
    _RELEVANT = {"environment_jump", "lighting_discontinuity"}

    def score(self, shot_id: str, context: dict[str, Any]) -> float:
        return _penalty_score(context.get("scene_violations", []), self._RELEVANT)


class StyleConsistencyMetric(IQualityMetric):
    """Penalizes StyleLockEngine.check_drift() findings for this shot."""

    metric_id = "style_consistency"

    def score(self, shot_id: str, context: dict[str, Any]) -> float:
        return _penalty_score(context.get("style_violations", []))


class CompositionQualityMetric(IQualityMetric):
    """Penalizes framing/blocking/timing violations that make a shot read
    as poorly composed rather than merely discontinuous."""

    metric_id = "composition_quality"
    _RELEVANT = {"entry_exit_mismatch", "timing_gap", "object_location_conflict", "shot_rhythm_break"}

    def score(self, shot_id: str, context: dict[str, Any]) -> float:
        combined = [*context.get("scene_violations", []), *context.get("camera_violations", [])]
        return _penalty_score(combined, self._RELEVANT)


class PromptAdherenceMetric(IQualityMetric):
    """Surfaces PromptScorer's own adherence_estimate - the best
    available estimate of whether the rendered shot matched its prompt
    without a real vision-language judge in the loop (see
    IEmbeddingProvider)."""

    metric_id = "prompt_adherence"

    def score(self, shot_id: str, context: dict[str, Any]) -> float:
        prompt_score = context.get("prompt_score")
        return float(prompt_score["adherence_estimate"]) if prompt_score else 1.0


class MotionQualityMetric(IQualityMetric):
    """Penalizes motion/camera-direction flips that would read as jarring
    or physically inconsistent movement."""

    metric_id = "motion_quality"
    _SCENE_RELEVANT = {"motion_direction_flip"}
    _CAMERA_RELEVANT = {"camera_direction_flip", "shot_rhythm_break"}

    def score(self, shot_id: str, context: dict[str, Any]) -> float:
        scene_score = _penalty_score(context.get("scene_violations", []), self._SCENE_RELEVANT)
        camera_score = _penalty_score(context.get("camera_violations", []), self._CAMERA_RELEVANT)
        return round(min(scene_score, camera_score), 4)


_BUILTIN_METRICS = (
    IdentityConsistencyMetric,
    CameraConsistencyMetric,
    LightingConsistencyMetric,
    StyleConsistencyMetric,
    CompositionQualityMetric,
    PromptAdherenceMetric,
    MotionQualityMetric,
)


def register_defaults() -> None:
    """Registers every built-in IQualityMetric into
    QUALITY_METRIC_REGISTRY, keyed by metric_id. Idempotent."""
    for metric_cls in _BUILTIN_METRICS:
        QUALITY_METRIC_REGISTRY.register_if_absent(metric_cls.metric_id, metric_cls)


class SceneQualityAnalyzerError(Exception):
    """Raised when an assembled QualityReport fails schema validation."""


class SceneQualityAnalyzer:
    """Produces a QualityReport (quality_report.schema.json) for a shot
    from already-computed continuity/style/prompt signals - never from
    inspecting rendered pixels (see IEmbeddingProvider for why that's
    prepared, not implemented). Requires `register_defaults()` to have
    been called first, same convention as TransitionEngine/
    PromptIntelligenceEngine's plugin registries."""

    def analyze(
        self,
        project_id: str,
        shot_id: str,
        *,
        scene_violations: list[dict[str, Any]] | None = None,
        camera_violations: list[dict[str, Any]] | None = None,
        style_violations: list[dict[str, Any]] | None = None,
        prompt_score: dict[str, float] | None = None,
        repair_threshold: float = _DEFAULT_REPAIR_THRESHOLD,
    ) -> dict[str, Any]:
        context = {
            "scene_violations": scene_violations or [],
            "camera_violations": camera_violations or [],
            "style_violations": style_violations or [],
            "prompt_score": prompt_score,
        }

        scores: dict[str, float] = {}
        for metric_id in (
            "identity_consistency",
            "camera_consistency",
            "lighting_consistency",
            "style_consistency",
            "composition_quality",
            "prompt_adherence",
            "motion_quality",
        ):
            metric: IQualityMetric = QUALITY_METRIC_REGISTRY.create(metric_id)
            scores[metric_id] = metric.score(shot_id, context)
        scores["overall"] = round(sum(scores.values()) / len(scores), 4)

        all_violations = [
            *context["scene_violations"],
            *context["camera_violations"],
            *context["style_violations"],
        ]
        issues = [
            {
                "category": _CATEGORY_FOR_VIOLATION.get(v["violation_type"], "composition"),
                "severity": v["severity"],
                "description": v["description"],
            }
            for v in all_violations
        ]
        repair_recommended = scores["overall"] < repair_threshold or any(
            v["severity"] == "critical" for v in all_violations
        )

        report: dict[str, Any] = {
            "schema_version": "1.0",
            "report_id": new_id("qual"),
            "project_id": project_id,
            "shot_id": shot_id,
            "scores": scores,
            "issues": issues,
            "repair_recommended": repair_recommended,
            "embeddings_used": False,
            "generated_at": now_iso(),
        }
        try:
            schemas.validate(report, "quality_report")
        except Exception as exc:  # noqa: BLE001
            raise SceneQualityAnalyzerError(f"Assembled QualityReport failed validation: {exc}") from exc
        return report
