from __future__ import annotations

import uuid
from typing import Any

import schemas
from asset_manager import AssetManager


class WatermarkEngineError(Exception):
    pass


class WatermarkEngine:
    """Builds a Timeline's branding: a logo overlay (applied by
    FfmpegCompositor as a corner overlay throughout playback, via
    Timeline.watermark) and/or intro/outro clips. Intro/outro are
    inserted as real Timeline video_clips - prepended/appended with a
    plain hard cut into/out of the branding clip by default - reusing
    the exact same transition machinery every other clip uses rather
    than inventing a separate "branding clip" code path in
    FfmpegCompositor. `Timeline.watermark.intro_asset_id`/
    `outro_asset_id` end up recording *which* asset was used, for
    reference/audit - FfmpegCompositor never reads those two fields
    itself, only `logo_asset_id`/`logo_position`/`logo_opacity`/
    `logo_scale`.
    """

    def __init__(self, asset_manager: AssetManager) -> None:
        self._assets = asset_manager

    def with_logo_overlay(
        self,
        timeline: dict[str, Any],
        logo_asset_id: str,
        position: str = "bottom_right",
        opacity: float = 0.8,
        scale: float = 0.15,
    ) -> dict[str, Any]:
        if self._assets.get(logo_asset_id) is None:
            raise WatermarkEngineError(f"No such asset: {logo_asset_id}")

        updated = dict(timeline)
        watermark = dict(updated.get("watermark") or {})
        watermark.update(
            {
                "logo_asset_id": logo_asset_id,
                "logo_position": position,
                "logo_opacity": opacity,
                "logo_scale": scale,
            }
        )
        updated["watermark"] = watermark
        schemas.validate(updated, "timeline")
        return updated

    def with_intro(self, timeline: dict[str, Any], intro_asset_id: str, duration_sec: float) -> dict[str, Any]:
        return self._insert_branding_clip(timeline, intro_asset_id, duration_sec, position="intro")

    def with_outro(self, timeline: dict[str, Any], outro_asset_id: str, duration_sec: float) -> dict[str, Any]:
        return self._insert_branding_clip(timeline, outro_asset_id, duration_sec, position="outro")

    def _insert_branding_clip(
        self, timeline: dict[str, Any], asset_id: str, duration_sec: float, position: str
    ) -> dict[str, Any]:
        asset = self._assets.get(asset_id)
        if asset is None:
            raise WatermarkEngineError(f"No such asset: {asset_id}")

        clip = {
            "clip_id": f"clip_{uuid.uuid4().hex[:12]}",
            "shot_id": f"branding_{position}",
            "source_uri": asset["versions"][-1]["uri"],
            "duration_sec": duration_sec,
        }
        clips = list(timeline["video_clips"])
        if position == "intro":
            clips.insert(0, clip)
        else:
            clips.append(clip)

        updated = dict(timeline)
        updated["video_clips"] = clips
        if "total_duration_sec" in timeline:
            updated["total_duration_sec"] = round(timeline["total_duration_sec"] + duration_sec, 3)

        watermark = dict(updated.get("watermark") or {})
        watermark[f"{position}_asset_id"] = asset_id
        updated["watermark"] = watermark

        schemas.validate(updated, "timeline")
        return updated
