from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import schemas
from post_processing.subtitle_generator import SubtitleGenerator


class AssetPackager:
    """Bundles the final video export, thumbnails, and subtitle files
    into one RenderManifest (render_manifest.schema.json) - the single
    record handed to a caller (frontend/API/CDN upload) as "the finished
    thing" for a project.
    """

    def __init__(self, output_dir: str | Path = "./.docker-data/manifests") -> None:
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._subtitles = SubtitleGenerator()

    def package(
        self,
        project_id: str,
        export_result: dict[str, Any],
        thumbnails: list[dict[str, Any]] | None = None,
        subtitle_tracks: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """`export_result` is ExportService.export()'s return dict.
        `thumbnails` items must already be shaped as
        {"asset_id", "uri", "kind", "timestamp_sec"} (ThumbnailEngine's
        AssetRecord output plus a caller-assigned `kind`). `subtitle_tracks`
        are SubtitleTrack dicts (subtitle_track.schema.json) - each
        non-burned-in track is serialized to a real SRT and WebVTT file
        on disk and referenced by URI; a burned-in track has no separate
        file (it's already in the video's pixels), so its manifest entry
        points at the video asset's own URI purely as a record that it
        exists."""
        self._output_dir.mkdir(parents=True, exist_ok=True)

        subtitle_entries: list[dict[str, Any]] = []
        for track in subtitle_tracks or []:
            if track.get("burned_in"):
                subtitle_entries.append(
                    {"language": track["language"], "format": "srt", "uri": export_result["uri"], "burned_in": True}
                )
                continue

            srt_path = self._output_dir / f"{project_id}_{track['language']}.srt"
            srt_path.write_text(self._subtitles.to_srt(track))
            subtitle_entries.append(
                {
                    "language": track["language"],
                    "format": "srt",
                    "uri": f"file://{srt_path.resolve()}",
                    "burned_in": False,
                }
            )

            vtt_path = self._output_dir / f"{project_id}_{track['language']}.vtt"
            vtt_path.write_text(self._subtitles.to_vtt(track))
            subtitle_entries.append(
                {
                    "language": track["language"],
                    "format": "vtt",
                    "uri": f"file://{vtt_path.resolve()}",
                    "burned_in": False,
                }
            )

        manifest = {
            "schema_version": "1.0",
            "manifest_id": f"manifest_{uuid.uuid4().hex[:12]}",
            "project_id": project_id,
            "video": {
                "asset_id": export_result["asset_id"],
                "uri": export_result["uri"],
                "format": export_result["format"],
                "resolution": export_result["resolution"],
                "fps": export_result["fps"],
                "duration_sec": export_result["duration_sec"],
                "codec": export_result["codec"],
            },
            "thumbnails": thumbnails or [],
            "subtitles": subtitle_entries,
            "metadata": metadata or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        schemas.validate(manifest, "render_manifest")
        return manifest
