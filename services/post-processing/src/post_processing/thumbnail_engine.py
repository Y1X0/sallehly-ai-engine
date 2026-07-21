from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from asset_manager import AssetManager

from .ffmpeg_utils import run_ffmpeg


class ThumbnailEngine:
    """Extracts real thumbnail images from a video clip via ffmpeg
    (`-ss <t> -vframes 1`) and registers them with AssetManager as
    kind="preview" (asset_record.schema.json already supports this kind
    - no new schema needed). No ML/scene-detection is involved: "scene
    thumbnails" here means one representative frame per shot (its
    midpoint, by default), and "auto thumbnail" means a project-level
    cover frame - both real, deterministic ffmpeg operations rather than
    a content-aware "best frame" selection (that would need a real
    vision model, out of scope here).
    """

    def __init__(
        self, asset_manager: AssetManager, output_dir: str | Path = "./.docker-data/thumbnails"
    ) -> None:
        self._assets = asset_manager
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def extract_keyframe(
        self,
        project_id: str,
        source_uri: str,
        timestamp_sec: float,
        shot_id: str | None = None,
    ) -> dict[str, Any]:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        output_path = self._output_dir / f"{project_id}_{shot_id or 'cover'}_{uuid.uuid4().hex[:8]}.jpg"
        run_ffmpeg(
            ["-ss", str(timestamp_sec), "-i", source_uri, "-vframes", "1", "-q:v", "2", str(output_path)]
        )
        return self._assets.register(
            project_id=project_id,
            shot_id=shot_id,
            kind="preview",
            uri=f"file://{output_path.resolve()}",
            metadata={"timestamp_sec": timestamp_sec, "source": "keyframe"},
        )

    def scene_thumbnail(
        self, project_id: str, shot_id: str, source_uri: str, duration_sec: float
    ) -> dict[str, Any]:
        """The shot's midpoint frame - a representative image for that
        shot without any content analysis."""
        return self.extract_keyframe(project_id, source_uri, timestamp_sec=duration_sec / 2, shot_id=shot_id)

    def auto_thumbnail(self, project_id: str, source_uri: str, duration_sec: float) -> dict[str, Any]:
        """A project-level cover thumbnail - the midpoint of whichever
        clip the caller passes (conventionally the assembled master, or
        the first shot's clip if the master isn't composed yet)."""
        return self.extract_keyframe(project_id, source_uri, timestamp_sec=duration_sec / 2, shot_id=None)
