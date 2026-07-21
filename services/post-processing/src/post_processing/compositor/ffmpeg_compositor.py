from __future__ import annotations

from pathlib import Path
from typing import Any

from asset_manager import AssetManager
from video_composition_sdk import CompositionResult, IRenderCompositor, SubtitleTrack, Timeline, Transition

from ..audio_pipeline import AudioPipeline
from ..ffmpeg_utils import probe, run_ffmpeg
from ..subtitle_generator import SubtitleGenerator
from ..transitions import TransitionEngine


class FfmpegCompositorError(Exception):
    pass


class FfmpegCompositor(IRenderCompositor):
    """Real, executable IRenderCompositor: builds one ffmpeg command
    that normalizes every clip to the Timeline's resolution/fps,
    stitches them with the resolved transitions (a hard cut uses
    ffmpeg's `concat` filter; every other transition uses `xfade` with
    the plugin-resolved preset/duration), mixes in audio tracks, burns
    in a subtitle track if requested, overlays a watermark if the
    Timeline carries one, and encodes the result to `output_path`.

    Ordering note on `xfade`: ffmpeg's `xfade` filter has a documented
    edge case where `offset` equal to (or greater than) the first
    input's duration collapses the output almost entirely rather than
    producing a full concatenation - discovered empirically while
    building this class. Hard cuts are therefore never expressed as a
    zero-duration `xfade`; they always use `concat`, which has no such
    edge case and is the semantically correct operation for a real cut
    anyway.
    """

    def __init__(self, asset_manager: AssetManager | None = None) -> None:
        self._assets = asset_manager
        self._transitions = TransitionEngine()
        self._audio = AudioPipeline()
        self._subtitles = SubtitleGenerator()

    def compose(
        self,
        timeline: Timeline,
        output_path: str | Path,
        subtitle_track: SubtitleTrack | None = None,
    ) -> CompositionResult:
        if not timeline.video_clips:
            raise FfmpegCompositorError("Timeline has no video_clips")

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        width, height = timeline.resolution.split("x")
        inputs: list[str] = [clip.source_uri for clip in timeline.video_clips]
        filter_parts, video_out_label, total_video_duration = self._build_video_chain(
            timeline, width, height
        )

        watermark_uri = self._resolve_watermark_uri(timeline)
        if watermark_uri is not None:
            inputs.append(watermark_uri)
            video_out_label = self._apply_watermark(filter_parts, video_out_label, len(inputs) - 1, timeline)

        if subtitle_track is not None:
            video_out_label = self._apply_subtitles(filter_parts, video_out_label, subtitle_track)

        audio_input_offset = len(inputs)
        audio_track_dicts = [self._audio_track_to_dict(t) for t in timeline.audio_tracks]
        input_index_by_track_id = {
            track["track_id"]: audio_input_offset + i for i, track in enumerate(audio_track_dicts)
        }
        for track in timeline.audio_tracks:
            inputs.append(track.source_uri)

        audio_mix = self._audio.build_mix_filter(audio_track_dicts, input_index_by_track_id)
        if audio_mix is not None:
            audio_filter, audio_out_label = audio_mix
            filter_parts.append(audio_filter)
        else:
            audio_out_label = None

        args: list[str] = []
        for source in inputs:
            args += ["-i", source]
        args += ["-filter_complex", ";".join(filter_parts)]
        args += ["-map", f"[{video_out_label}]"]
        if audio_out_label is not None:
            args += ["-map", f"[{audio_out_label}]"]
        args += [
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
        ]
        if audio_out_label is not None:
            args += ["-c:a", "aac", "-b:a", "192k"]
        args += [str(output_path)]

        run_ffmpeg(args)

        probed = probe(output_path)
        video_stream = next(s for s in probed["streams"] if s["codec_type"] == "video")
        return CompositionResult(
            output_uri=f"file://{output_path.resolve()}",
            duration_sec=float(probed["format"]["duration"]),
            resolution=f"{video_stream['width']}x{video_stream['height']}",
            fps=timeline.fps,
        )

    def _build_video_chain(
        self, timeline: Timeline, width: str, height: str
    ) -> tuple[list[str], str, float]:
        normalize = (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps={timeline.fps}"
        )

        filter_parts: list[str] = []
        clips = timeline.video_clips
        for i, clip in enumerate(clips):
            ops = [normalize]
            if i == 0 and clip.transition_in is not None:
                recipe = self._transitions.resolve(clip.transition_in)
                if recipe.mode == "fade_from_black":
                    ops.append(f"fade=t=in:st=0:d={recipe.duration_sec}")
            if i == len(clips) - 1 and clip.transition_out is not None:
                recipe = self._transitions.resolve(clip.transition_out)
                if recipe.mode == "fade_to_black":
                    fade_start = max(0.0, clip.duration_sec - recipe.duration_sec)
                    ops.append(f"fade=t=out:st={fade_start}:d={recipe.duration_sec}")
            filter_parts.append(f"[{i}:v]{','.join(ops)}[v{i}]")

        current_label = "v0"
        current_duration = clips[0].duration_sec
        for i in range(1, len(clips)):
            prev_clip = clips[i - 1]
            recipe = self._transitions.resolve(prev_clip.transition_out) if prev_clip.transition_out else None
            next_label = f"vm{i}"
            if recipe is not None and recipe.mode == "xfade":
                offset = current_duration - recipe.duration_sec
                filter_parts.append(
                    f"[{current_label}][v{i}]xfade=transition={recipe.xfade_transition}:"
                    f"duration={recipe.duration_sec}:offset={offset:.6f}[{next_label}]"
                )
                current_duration = current_duration + clips[i].duration_sec - recipe.duration_sec
            else:
                filter_parts.append(f"[{current_label}][v{i}]concat=n=2:v=1:a=0[{next_label}]")
                current_duration = current_duration + clips[i].duration_sec
            current_label = next_label

        return filter_parts, current_label, current_duration

    def _resolve_watermark_uri(self, timeline: Timeline) -> str | None:
        if timeline.watermark is None or timeline.watermark.logo_asset_id is None:
            return None
        if self._assets is None:
            raise FfmpegCompositorError("Timeline has a watermark but no AssetManager was provided to resolve it")
        asset = self._assets.get(timeline.watermark.logo_asset_id)
        if asset is None:
            raise FfmpegCompositorError(f"No such asset: {timeline.watermark.logo_asset_id}")
        return asset["versions"][-1]["uri"]

    def _apply_watermark(
        self, filter_parts: list[str], video_label: str, watermark_input_index: int, timeline: Timeline
    ) -> str:
        watermark = timeline.watermark
        scale_expr = f"scale=iw*{watermark.logo_scale}:-1"
        filter_parts.append(f"[{watermark_input_index}:v]{scale_expr},format=rgba,colorchannelmixer=aa={watermark.logo_opacity}[wm]")
        position = {
            "top_left": "10:10",
            "top_right": "W-w-10:10",
            "bottom_left": "10:H-h-10",
            "bottom_right": "W-w-10:H-h-10",
            "center": "(W-w)/2:(H-h)/2",
        }[watermark.logo_position]
        out_label = "vwm"
        filter_parts.append(f"[{video_label}][wm]overlay={position}[{out_label}]")
        return out_label

    def _apply_subtitles(
        self, filter_parts: list[str], video_label: str, subtitle_track: SubtitleTrack
    ) -> str:
        srt_content = self._subtitles.to_srt(_subtitle_track_to_dict(subtitle_track))
        srt_path = Path(f"/tmp/sallehly_subtitles_{subtitle_track.track_id}.srt")
        srt_path.write_text(srt_content)
        force_style = self._subtitles.burn_in_force_style(subtitle_track.style_preset_id)
        out_label = "vsub"
        filter_parts.append(f"[{video_label}]subtitles={srt_path}:force_style='{force_style}'[{out_label}]")
        return out_label

    def _audio_track_to_dict(self, track: Any) -> dict[str, Any]:
        d = {
            "track_id": track.track_id,
            "kind": track.kind,
            "source_uri": track.source_uri,
            "start_time_sec": track.start_time_sec,
            "volume_db": track.volume_db,
            "fade_in_sec": track.fade_in_sec,
            "fade_out_sec": track.fade_out_sec,
        }
        if track.duration_sec is not None:
            d["duration_sec"] = track.duration_sec
        if track.volume_automation:
            d["volume_automation"] = [{"t": t, "volume_db": v} for t, v in track.volume_automation]
        return d


def _subtitle_track_to_dict(track: SubtitleTrack) -> dict[str, Any]:
    return {
        "track_id": track.track_id,
        "project_id": track.project_id,
        "language": track.language,
        "style_preset_id": track.style_preset_id,
        "burned_in": track.burned_in,
        "cues": [
            {
                "cue_id": cue.cue_id,
                "start_sec": cue.start_sec,
                "end_sec": cue.end_sec,
                "text": cue.text,
                **({"shot_id": cue.shot_id} if cue.shot_id else {}),
            }
            for cue in track.cues
        ],
    }


def timeline_from_dict(timeline_dict: dict[str, Any]) -> Timeline:
    """Converts a schema-validated timeline dict (what TimelineBuilder/
    AudioPipeline/WatermarkEngine produce) into the Timeline dataclass
    IRenderCompositor.compose() requires - the same dict->dataclass
    boundary pattern GenerationPipeline uses for RenderSpec (ADR 0009)."""
    from video_composition_sdk import AudioTrack, BrandingPackage, VideoClip

    def _transition(d: dict[str, Any] | None) -> Transition | None:
        if d is None:
            return None
        return Transition(type=d["type"], duration_sec=d.get("duration_sec", 0.0), plugin_id=d.get("plugin_id"), params=d.get("params", {}))

    video_clips = tuple(
        VideoClip(
            clip_id=c["clip_id"],
            shot_id=c["shot_id"],
            source_uri=c["source_uri"],
            duration_sec=c["duration_sec"],
            transition_in=_transition(c.get("transition_in")),
            transition_out=_transition(c.get("transition_out")),
        )
        for c in timeline_dict["video_clips"]
    )
    audio_tracks = tuple(
        AudioTrack(
            track_id=a["track_id"],
            kind=a["kind"],
            source_uri=a["source_uri"],
            start_time_sec=a["start_time_sec"],
            duration_sec=a.get("duration_sec"),
            volume_db=a.get("volume_db", 0.0),
            fade_in_sec=a.get("fade_in_sec", 0.0),
            fade_out_sec=a.get("fade_out_sec", 0.0),
            volume_automation=tuple((kf["t"], kf["volume_db"]) for kf in a.get("volume_automation", [])),
        )
        for a in timeline_dict.get("audio_tracks", [])
    )
    watermark = None
    if timeline_dict.get("watermark"):
        w = timeline_dict["watermark"]
        watermark = BrandingPackage(
            logo_asset_id=w.get("logo_asset_id"),
            logo_position=w.get("logo_position", "bottom_right"),
            logo_opacity=w.get("logo_opacity", 0.8),
            logo_scale=w.get("logo_scale", 0.15),
            intro_asset_id=w.get("intro_asset_id"),
            outro_asset_id=w.get("outro_asset_id"),
        )
    return Timeline(
        schema_version=timeline_dict["schema_version"],
        project_id=timeline_dict["project_id"],
        fps=timeline_dict["fps"],
        resolution=timeline_dict["resolution"],
        video_clips=video_clips,
        aspect_ratio=timeline_dict.get("aspect_ratio"),
        audio_tracks=audio_tracks,
        subtitle_track_id=timeline_dict.get("subtitle_track_id"),
        watermark=watermark,
        total_duration_sec=timeline_dict.get("total_duration_sec"),
    )


def subtitle_track_from_dict(track_dict: dict[str, Any]) -> SubtitleTrack:
    from video_composition_sdk import SubtitleCue

    cues = tuple(
        SubtitleCue(
            cue_id=c["cue_id"],
            start_sec=c["start_sec"],
            end_sec=c["end_sec"],
            text=c["text"],
            shot_id=c.get("shot_id"),
        )
        for c in track_dict["cues"]
    )
    return SubtitleTrack(
        track_id=track_dict["track_id"],
        project_id=track_dict["project_id"],
        language=track_dict["language"],
        cues=cues,
        style_preset_id=track_dict.get("style_preset_id", "default"),
        burned_in=track_dict.get("burned_in", False),
    )
