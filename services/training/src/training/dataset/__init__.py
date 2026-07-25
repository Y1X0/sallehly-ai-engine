from __future__ import annotations

from .captions import HeuristicCaptionProvider, VLMCaptionProvider
from .duplicates import EmbeddingDuplicateDetector, HashDuplicateDetector
from .interfaces import ICaptionProvider, IDatasetValidator, IDuplicateDetector, ValidationIssue, ValidationResult
from .manager import DatasetManager
from .metadata import ClipMetadata, FfprobeNotAvailableError, extract_clip_metadata
from .records import ClipRecord
from .split import assign_split, split_dataset
from .statistics import DatasetStatistics, compute_statistics
from .validator import DatasetValidator
from .versioning import (
    DatasetVersion,
    FilesystemDatasetVersionStore,
    IDatasetVersionStore,
    build_dataset_version,
    compute_version_id,
)

__all__ = [
    "ClipMetadata",
    "ClipRecord",
    "DatasetManager",
    "DatasetStatistics",
    "DatasetValidator",
    "DatasetVersion",
    "EmbeddingDuplicateDetector",
    "FfprobeNotAvailableError",
    "FilesystemDatasetVersionStore",
    "HashDuplicateDetector",
    "HeuristicCaptionProvider",
    "ICaptionProvider",
    "IDatasetValidator",
    "IDatasetVersionStore",
    "IDuplicateDetector",
    "VLMCaptionProvider",
    "ValidationIssue",
    "ValidationResult",
    "assign_split",
    "build_dataset_version",
    "compute_statistics",
    "compute_version_id",
    "extract_clip_metadata",
    "split_dataset",
]
