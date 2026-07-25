from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .types import ReferencePackage


class IReferenceConditioningAdapter(ABC):
    """Prepared interface for a future engine-adapter capability: consuming
    a ReferencePackage as real ControlNet/IP-Adapter conditioning input at
    generation time, beyond the existing plain `conditioning_images`
    passthrough already on RenderSpec (render_configuration.schema.json).

    No concrete implementation ships in Phase 7 - it requires an engine
    that actually supports image conditioning and an adapter that wires
    it up (see docs/adr/0013-cinematic-intelligence-layer.md). The
    Reference Image Engine still builds real ReferencePackages; this
    interface just documents where they would plug into generation
    later, without RenderSpec or any IVideoEngine implementation
    changing shape today."""

    @abstractmethod
    def supports(self, package: ReferencePackage) -> bool: ...

    @abstractmethod
    def apply(self, package: ReferencePackage, render_spec: dict[str, Any]) -> dict[str, Any]:
        """Returns a new RenderSpec-shaped dict with conditioning applied."""
        ...
