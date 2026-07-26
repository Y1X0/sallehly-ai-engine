from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import TrainingConfig
from ..dataset.records import ClipRecord


@dataclass(frozen=True)
class Wan22ManifestEntry:
    """One training sample in the exact shape a real Wan2.2
    fine-tuning script (musubi-tuner or a diffusers WanPipeline-based
    trainer) expects to read: a video path, a caption, and the
    resolution/frame-count/fps that path actually contains - mirroring
    the caption-format section of the Wan2.2 fine-tuning blueprint
    (structured metadata alongside the caption, not just a bare string).
    Deliberately independent of any specific trainer's manifest schema
    (musubi-tuner's, a custom one) since none is wired in yet - the
    field names here are the common denominator any of them can be
    mapped to when a real backend exists."""

    clip_id: str
    video_path: str
    caption: str
    width: int
    height: int
    num_frames: int
    fps: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "clip_id": self.clip_id,
            "video_path": self.video_path,
            "caption": self.caption,
            "width": self.width,
            "height": self.height,
            "num_frames": self.num_frames,
            "fps": self.fps,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Wan22ManifestEntry":
        return cls(
            clip_id=data["clip_id"],
            video_path=data["video_path"],
            caption=data["caption"],
            width=data["width"],
            height=data["height"],
            num_frames=data["num_frames"],
            fps=data["fps"],
        )


class Wan22DatasetAdapter:
    """Converts `ClipRecord`s - the real, ffprobe-backed records
    `training.dataset.DatasetManager` already produces - into Wan2.2
    training manifest entries. Pure metadata transformation: no video
    bytes are read or re-encoded here (that already happened once, for
    real, in `dataset.metadata.extract_clip_metadata`); this only
    validates and reshapes what's already known about each clip.

    Refuses (rather than silently skipping) any clip missing a caption
    or rights clearance - the same "never let something a human hasn't
    signed off on slip into a training run silently" posture
    `DatasetValidator` already takes.
    """

    def __init__(self, config: TrainingConfig) -> None:
        self._config = config

    def build_manifest(self, records: list[ClipRecord], *, split: str = "train") -> list[Wan22ManifestEntry]:
        entries: list[Wan22ManifestEntry] = []
        for record in records:
            if record.split != split:
                continue
            if not record.rights_cleared:
                raise ValueError(
                    f"clip {record.clip_id!r} is not rights_cleared - refusing to include "
                    "it in a Wan2.2 training manifest"
                )
            if not record.caption:
                raise ValueError(
                    f"clip {record.clip_id!r} has no caption - run DatasetManager.caption_all() "
                    "before building a Wan2.2 manifest"
                )
            num_frames = min(
                int(record.metadata.duration_sec * record.metadata.fps),
                self._config.max_frames,
            )
            if num_frames <= 0:
                raise ValueError(
                    f"clip {record.clip_id!r} resolves to {num_frames} usable frames "
                    f"(duration={record.metadata.duration_sec}s, fps={record.metadata.fps}) - unusable"
                )
            entries.append(
                Wan22ManifestEntry(
                    clip_id=record.clip_id,
                    video_path=record.source_uri,
                    caption=record.caption,
                    width=record.metadata.width,
                    height=record.metadata.height,
                    num_frames=num_frames,
                    fps=record.metadata.fps,
                )
            )

        if not entries:
            raise ValueError(f"No usable clips for split={split!r} - the resulting manifest would be empty")
        return entries

    def write_manifest_jsonl(
        self, records: list[ClipRecord], output_path: str | Path, *, split: str = "train"
    ) -> Path:
        entries = self.build_manifest(records, split=split)
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w") as f:
            for entry in entries:
                f.write(json.dumps(entry.to_dict()) + "\n")
        return path


def load_manifest_jsonl(path: str | Path) -> list[Wan22ManifestEntry]:
    entries = []
    with Path(path).open() as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(Wan22ManifestEntry.from_dict(json.loads(line)))
    return entries
