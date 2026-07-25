from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class IQualityMetric(ABC):
    """One entry in the Scene Quality Analyzer's plugin registry
    (config_sdk.registry.QUALITY_METRIC_REGISTRY, key = metric_id -
    'identity_consistency', 'camera_consistency', ...). Each built-in
    metric is a rule-based comparison against ContinuityReport/StyleLock/
    ProjectMemory state (see services/cinematic-intelligence's
    quality_analyzer.py); a future metric backed by a real perceptual
    model (CLIP/DINO via IEmbeddingProvider) plugs in under the same
    interface without changing SceneQualityAnalyzer."""

    metric_id: str

    @abstractmethod
    def score(self, shot_id: str, context: dict[str, Any]) -> float:
        """Returns a score in [0, 1]. `context` carries whatever state
        (ContinuityReport, StyleLock, ProjectMemory, PromptPackage, ...)
        this metric needs, keyed by the caller's convention - see
        SceneQualityAnalyzer.analyze for the exact keys it provides."""
        ...
