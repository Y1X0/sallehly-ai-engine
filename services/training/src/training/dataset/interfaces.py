from __future__ import annotations

from abc import ABC, abstractmethod

from ..validation import ValidationIssue, ValidationResult
from .records import ClipRecord

__all__ = [
    "ICaptionProvider",
    "IDatasetValidator",
    "IDuplicateDetector",
    "ValidationIssue",
    "ValidationResult",
]


class IDatasetValidator(ABC):
    """Checks one `ClipRecord` against real, checkable rules (rights
    clearance, duration/resolution/fps floors) - never a model call,
    always deterministic and instant. See `validator.py`'s
    `DatasetValidator` for the one implementation."""

    @abstractmethod
    def validate(self, record: ClipRecord) -> ValidationResult: ...


class ICaptionProvider(ABC):
    """Produces a training caption for one clip. `captions.py` has two
    implementations: `HeuristicCaptionProvider` (real, metadata-derived,
    always available) and `VLMCaptionProvider` (the real Stage 4
    integration point, raises `ModelUnavailableError` until a real
    vision-language model is wired in)."""

    @abstractmethod
    def generate_caption(self, record: ClipRecord) -> str: ...


class IDuplicateDetector(ABC):
    """Finds pairs of clips considered duplicates of each other, returned
    as `(clip_id, clip_id)` tuples. `duplicates.py` has two
    implementations: `HashDuplicateDetector` (real, exact-byte dedup via
    SHA-256, always available) and `EmbeddingDuplicateDetector` (the real
    near-duplicate integration point via perceptual embeddings, raises
    `ModelUnavailableError` when no embeddings are supplied). `embeddings`
    is keyword-only and optional precisely so `HashDuplicateDetector`
    can ignore it without the interface forcing every implementation to
    the lowest common denominator."""

    @abstractmethod
    def find_duplicates(
        self, records: list[ClipRecord], *, embeddings: dict[str, tuple[float, ...]] | None = None
    ) -> list[tuple[str, str]]: ...
