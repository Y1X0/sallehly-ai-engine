from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .types import QualityReport, RepairAction


class IRepairStrategy(ABC):
    """One entry in the Automatic Repair Engine's plugin registry
    (config_sdk.registry.REPAIR_STRATEGY_REGISTRY, key = repair_type).
    Given a QualityReport that recommended a repair, produces a
    RepairAction scoped to that report's single shot_id - a strategy must
    never touch any other shot. `context` carries whatever the calling
    engine already has in hand (ProjectMemory, the shot's current
    PromptPackage, StyleLock, ...) so a strategy doesn't have to re-fetch
    it. Same real-plugin-architecture pattern as ITransitionPlugin
    (packages/video-composition-sdk) - a custom repair strategy
    implements this exact interface and registers under its own key."""

    repair_type: str

    @abstractmethod
    def repair(self, quality_report: QualityReport, context: dict[str, Any]) -> RepairAction: ...
