from __future__ import annotations

from abc import ABC, abstractmethod


class IEmbeddingProvider(ABC):
    """Prepared interface for a future perceptual-embedding backend
    (CLIP/DINO or similar) that would let the Scene Quality Analyzer
    compare actual rendered pixels instead of metadata-derived heuristics.

    No concrete implementation ships in Phase 7 - it requires a deployed
    vision model, the same class of limitation as real GPU inference in
    workers/gpu-worker (see docs/adr/0013-cinematic-intelligence-layer.md
    and the root README's "genuinely unexecuted" section). Every
    Phase 7 quality/consistency score is computed from structured
    metadata (ContinuityReport, StyleLock, ProjectMemory, PromptPackage)
    rather than from this interface."""

    @abstractmethod
    def embed_image(self, asset_uri: str) -> tuple[float, ...]: ...

    @abstractmethod
    def similarity(self, embedding_a: tuple[float, ...], embedding_b: tuple[float, ...]) -> float:
        """Returns a similarity score in [0, 1]."""
        ...
