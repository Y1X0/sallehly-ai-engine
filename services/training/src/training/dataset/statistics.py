from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from .records import ClipRecord


@dataclass(frozen=True)
class DatasetStatistics:
    """Real aggregate facts about a set of `ClipRecord`s - pure
    arithmetic over already-extracted metadata, no model or GPU
    involved. This is what a dataset-readiness review (Phase 9 roadmap
    Stage 2/3) actually reads before deciding a dataset is large/clean
    enough to train against."""

    clip_count: int
    total_duration_sec: float
    mean_duration_sec: float
    resolution_counts: dict[str, int]
    fps_counts: dict[str, int]
    split_counts: dict[str, int]
    caption_coverage: float
    rights_cleared_fraction: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "clip_count": self.clip_count,
            "total_duration_sec": self.total_duration_sec,
            "mean_duration_sec": self.mean_duration_sec,
            "resolution_counts": self.resolution_counts,
            "fps_counts": self.fps_counts,
            "split_counts": self.split_counts,
            "caption_coverage": self.caption_coverage,
            "rights_cleared_fraction": self.rights_cleared_fraction,
        }


def compute_statistics(records: list[ClipRecord]) -> DatasetStatistics:
    if not records:
        return DatasetStatistics(
            clip_count=0,
            total_duration_sec=0.0,
            mean_duration_sec=0.0,
            resolution_counts={},
            fps_counts={},
            split_counts={},
            caption_coverage=0.0,
            rights_cleared_fraction=0.0,
        )

    total_duration = sum(r.metadata.duration_sec for r in records)
    resolution_counts = Counter(r.metadata.resolution for r in records)
    fps_counts = Counter(f"{r.metadata.fps:g}" for r in records)
    split_counts = Counter(r.split or "unassigned" for r in records)
    captioned = sum(1 for r in records if r.caption)
    rights_cleared = sum(1 for r in records if r.rights_cleared)

    return DatasetStatistics(
        clip_count=len(records),
        total_duration_sec=round(total_duration, 3),
        mean_duration_sec=round(total_duration / len(records), 3),
        resolution_counts=dict(resolution_counts),
        fps_counts=dict(fps_counts),
        split_counts=dict(split_counts),
        caption_coverage=round(captioned / len(records), 4),
        rights_cleared_fraction=round(rights_cleared / len(records), 4),
    )
