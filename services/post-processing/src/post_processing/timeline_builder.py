from __future__ import annotations

import uuid
from typing import Any

import schemas

# Maps shot.schema.json's transition_in/transition_out vocabulary onto
# transition.schema.json's Transition.type + a sensible default duration.
# "cut" carries no special effect (None); ShotPlanner (Phase 1) sets it
# on every shot except the first one's transition_in, which defaults to
# "fade_from_black" - see services/shot-planner/src/shot_planner/planner.py.
_TRANSITION_IN_MAP: dict[str, tuple[str, float]] = {
    "dissolve": ("dissolve", 0.5),
    "match_cut": ("match_cut", 0.2),
    "wipe": ("wipe", 0.5),
    "fade_from_black": ("fade_in", 0.6),
}
_TRANSITION_OUT_MAP: dict[str, tuple[str, float]] = {
    "cut": ("cinematic_cut", 0.0),
    "dissolve": ("dissolve", 0.5),
    "match_cut": ("match_cut", 0.2),
    "wipe": ("wipe", 0.5),
    "fade_to_black": ("fade_out", 0.6),
}

# Fallback per aspect_ratio when no RenderPlan is supplied to infer an
# actual encoded resolution from.
_DEFAULT_RESOLUTION_BY_ASPECT: dict[str, str] = {
    "16:9": "1920x1080",
    "9:16": "1080x1920",
    "1:1": "1080x1080",
    "21:9": "2560x1080",
    "4:5": "1080x1350",
}


class TimelineBuilderError(Exception):
    """Raised when a shot has no corresponding video asset, or the
    assembled Timeline fails schema validation."""


class TimelineBuilder:
    """Sequences a completed project's per-shot RawClips into a Timeline
    (packages/schemas/json/timeline.schema.json). Shot order and
    transitions come straight from the DirectorPlan (Shot.transition_in/
    transition_out, already decided by the Shot Planner in Phase 1) -
    the Timeline Builder never invents creative sequencing decisions, it
    only translates already-decided ones into the post-production
    pipeline's contract. Audio tracks, a subtitle track, and a watermark
    are layered on separately (AudioPipeline, SubtitleGenerator,
    WatermarkEngine) and merged in via `with_audio_tracks`/
    `with_subtitle_track`/`with_watermark`.
    """

    def build(
        self,
        director_plan: dict[str, Any],
        video_assets_by_shot_id: dict[str, dict[str, Any]],
        render_plan: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """`video_assets_by_shot_id` maps shot_id -> AssetRecord dict
        (asset_record.schema.json, kind="video") - the caller resolves
        which asset_id belongs to which shot_id (GenerationJob.shot_id /
        AssetRecord.shot_id). `render_plan` is optional and, when given,
        supplies fps/resolution from its RenderSpecs rather than the
        aspect-ratio-based defaults."""
        shots = self._ordered_shots(director_plan)
        if not shots:
            raise TimelineBuilderError(f"DirectorPlan for {director_plan['project_id']} has no shots")

        video_clips: list[dict[str, Any]] = []
        total_duration = 0.0
        for shot in shots:
            asset = video_assets_by_shot_id.get(shot["shot_id"])
            if asset is None:
                raise TimelineBuilderError(f"No video asset for shot {shot['shot_id']}")

            clip: dict[str, Any] = {
                "clip_id": f"clip_{uuid.uuid4().hex[:12]}",
                "shot_id": shot["shot_id"],
                "source_uri": asset["versions"][-1]["uri"],
                "duration_sec": shot["duration_sec"],
            }
            transition_in = self._resolve(shot.get("transition_in", "cut"), _TRANSITION_IN_MAP)
            if transition_in is not None:
                clip["transition_in"] = transition_in
            transition_out = self._resolve(shot.get("transition_out", "cut"), _TRANSITION_OUT_MAP)
            if transition_out is not None:
                clip["transition_out"] = transition_out

            video_clips.append(clip)
            total_duration += shot["duration_sec"]

        fps, resolution = self._resolve_fps_and_resolution(director_plan, render_plan)

        timeline: dict[str, Any] = {
            "schema_version": "1.0",
            "project_id": director_plan["project_id"],
            "fps": fps,
            "resolution": resolution,
            "video_clips": video_clips,
            "total_duration_sec": round(total_duration, 3),
        }
        if director_plan.get("aspect_ratio"):
            timeline["aspect_ratio"] = director_plan["aspect_ratio"]

        try:
            schemas.validate(timeline, "timeline")
        except Exception as exc:  # noqa: BLE001 - re-raised as a TimelineBuilderError for callers
            raise TimelineBuilderError(f"Assembled Timeline failed validation: {exc}") from exc
        return timeline

    def _ordered_shots(self, director_plan: dict[str, Any]) -> list[dict[str, Any]]:
        shots: list[dict[str, Any]] = []
        for scene in sorted(director_plan["scenes"], key=lambda s: s["order"]):
            shots.extend(sorted(scene["shots"], key=lambda s: s["order"]))
        return shots

    def _resolve(self, shot_value: str, mapping: dict[str, tuple[str, float]]) -> dict[str, Any] | None:
        resolved = mapping.get(shot_value)
        if resolved is None:
            return None
        transition_type, duration_sec = resolved
        return {"type": transition_type, "duration_sec": duration_sec}

    def _resolve_fps_and_resolution(
        self, director_plan: dict[str, Any], render_plan: dict[str, Any] | None
    ) -> tuple[int, str]:
        if render_plan and render_plan.get("render_specs"):
            first_spec = render_plan["render_specs"][0]
            return first_spec["fps"], first_spec["resolution"]
        aspect_ratio = director_plan.get("aspect_ratio", "16:9")
        return 24, _DEFAULT_RESOLUTION_BY_ASPECT.get(aspect_ratio, "1920x1080")
