from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .metadata import ClipMetadata


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ClipRecord:
    """One raw training clip's full dataset-pipeline state - identity,
    real ffprobe metadata, and everything the pipeline stages
    (caption/validate/split) attach as they run. `rights_cleared`
    defaults to `False` deliberately: `DatasetValidator` treats an
    unrights-cleared clip as a hard validation error (Phase 9 roadmap
    Stage 2 - "every clip needs a documented, auditable rights chain
    before training") rather than something that's easy to silently
    ingest anyway."""

    clip_id: str
    source_uri: str
    metadata: ClipMetadata
    caption: str | None = None
    split: str | None = None
    tags: list[str] = field(default_factory=list)
    rights_cleared: bool = False
    added_at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "clip_id": self.clip_id,
            "source_uri": self.source_uri,
            "metadata": self.metadata.to_dict(),
            "caption": self.caption,
            "split": self.split,
            "tags": self.tags,
            "rights_cleared": self.rights_cleared,
            "added_at": self.added_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ClipRecord":
        return cls(
            clip_id=data["clip_id"],
            source_uri=data["source_uri"],
            metadata=ClipMetadata.from_dict(data["metadata"]),
            caption=data.get("caption"),
            split=data.get("split"),
            tags=list(data.get("tags") or []),
            rights_cleared=data.get("rights_cleared", False),
            added_at=data["added_at"],
        )
