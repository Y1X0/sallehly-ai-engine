from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import schemas
from asset_manager import AssetManager
from post_processing.ffmpeg_utils import probe, run_ffmpeg

from .quality_presets import FORMAT_CODECS, QUALITY_PRESETS


class ExportServiceError(Exception):
    pass


class ExportService:
    """Produces final delivery artifacts from an assembled master video
    (services/post-processing's FfmpegCompositor output): a real ffmpeg
    re-encode to the requested container format (mp4/mov/webm) and
    quality preset (720p/1080p/1440p/4k), registered with AssetManager
    as a project-level video asset (shot_id=None, one AssetRecord per
    export - re-exporting at a different preset is a new version of the
    same "final video" asset key)."""

    def __init__(self, asset_manager: AssetManager, output_dir: str | Path = "./.docker-data/exports") -> None:
        self._assets = asset_manager
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def export(self, project_id: str, master_source_uri: str, export_spec: dict[str, Any]) -> dict[str, Any]:
        schemas.validate(export_spec, "export_spec")

        fmt = export_spec["format"]
        if fmt not in FORMAT_CODECS:
            raise ExportServiceError(f"Unsupported format '{fmt}'. Available: {', '.join(sorted(FORMAT_CODECS))}")
        quality_preset = export_spec["quality_preset"]
        if quality_preset not in QUALITY_PRESETS:
            raise ExportServiceError(
                f"Unsupported quality_preset '{quality_preset}'. Available: {', '.join(sorted(QUALITY_PRESETS))}"
            )

        preset = QUALITY_PRESETS[quality_preset]
        codec = FORMAT_CODECS[fmt]
        width, height = preset["resolution"].split("x")
        video_bitrate = export_spec.get("video_bitrate_kbps", preset["video_bitrate_kbps"])
        audio_bitrate = export_spec.get("audio_bitrate_kbps", preset["audio_bitrate_kbps"])

        self._output_dir.mkdir(parents=True, exist_ok=True)
        output_path = self._output_dir / f"{project_id}_{uuid.uuid4().hex[:12]}.{fmt}"

        args = [
            "-i",
            master_source_uri,
            "-vf",
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black",
            "-c:v",
            codec["video_codec"],
            "-b:v",
            f"{video_bitrate}k",
            "-c:a",
            codec["audio_codec"],
            "-b:a",
            f"{audio_bitrate}k",
            *codec["extra_args"],
            str(output_path),
        ]
        run_ffmpeg(args)

        probed = probe(output_path)
        video_stream = next(s for s in probed["streams"] if s["codec_type"] == "video")

        asset = self._assets.register(
            project_id=project_id,
            kind="video",
            uri=f"file://{output_path.resolve()}",
            metadata={
                "format": fmt,
                "quality_preset": quality_preset,
                "codec": codec["video_codec"],
                "video_bitrate_kbps": video_bitrate,
                "audio_bitrate_kbps": audio_bitrate,
            },
        )

        return {
            "asset_id": asset["asset_id"],
            "uri": asset["versions"][-1]["uri"],
            "format": fmt,
            "resolution": f"{video_stream['width']}x{video_stream['height']}",
            "fps": _parse_fps(video_stream.get("r_frame_rate", "0/1")),
            "duration_sec": float(probed["format"]["duration"]),
            "codec": codec["video_codec"],
        }


def _parse_fps(r_frame_rate: str) -> int:
    numerator, _, denominator = r_frame_rate.partition("/")
    denominator = denominator or "1"
    return round(int(numerator) / int(denominator))
