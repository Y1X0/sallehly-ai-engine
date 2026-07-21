from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Transition:
    """Mirrors packages/schemas/json/transition.schema.json."""

    type: str
    duration_sec: float = 0.0
    plugin_id: str | None = None
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VideoClip:
    """One entry in Timeline.video_clips."""

    clip_id: str
    shot_id: str
    source_uri: str
    duration_sec: float
    transition_in: Transition | None = None
    transition_out: Transition | None = None


@dataclass(frozen=True)
class AudioTrack:
    """One entry in Timeline.audio_tracks. `volume_automation` is a tuple
    of (t_seconds_from_track_start, volume_db) keyframes, sorted by t."""

    track_id: str
    kind: str  # music | sfx | voiceover
    source_uri: str
    start_time_sec: float
    duration_sec: float | None = None
    volume_db: float = 0.0
    fade_in_sec: float = 0.0
    fade_out_sec: float = 0.0
    volume_automation: tuple[tuple[float, float], ...] = ()


@dataclass(frozen=True)
class BrandingPackage:
    """Mirrors packages/schemas/json/branding_package.schema.json."""

    logo_asset_id: str | None = None
    logo_position: str = "bottom_right"
    logo_opacity: float = 0.8
    logo_scale: float = 0.15
    intro_asset_id: str | None = None
    outro_asset_id: str | None = None


@dataclass(frozen=True)
class Timeline:
    """Mirrors packages/schemas/json/timeline.schema.json - the sole
    input to IRenderCompositor.compose(). Produced by
    services/post-processing's TimelineBuilder; nothing upstream of it
    (CreativeDirector, CreativeCompiler, GenerationPipeline) knows this
    type exists, per the same layering ADR 0001 established for
    generation."""

    schema_version: str
    project_id: str
    fps: int
    resolution: str
    video_clips: tuple[VideoClip, ...]
    aspect_ratio: str | None = None
    audio_tracks: tuple[AudioTrack, ...] = ()
    subtitle_track_id: str | None = None
    watermark: BrandingPackage | None = None
    total_duration_sec: float | None = None


@dataclass(frozen=True)
class SubtitleCue:
    cue_id: str
    start_sec: float
    end_sec: float
    text: str
    shot_id: str | None = None


@dataclass(frozen=True)
class SubtitleTrack:
    """Mirrors packages/schemas/json/subtitle_track.schema.json."""

    track_id: str
    project_id: str
    language: str
    cues: tuple[SubtitleCue, ...]
    style_preset_id: str = "default"
    burned_in: bool = False


@dataclass(frozen=True)
class CompositionResult:
    """Output of IRenderCompositor.compose()."""

    output_uri: str
    duration_sec: float
    resolution: str
    fps: int


@dataclass(frozen=True)
class TransitionRecipe:
    """What ITransitionPlugin.resolve() returns: the operational meaning
    of a Transition, still engine-agnostic (no raw ffmpeg filter syntax
    here - that's IRenderCompositor's job to interpret). `mode="hard_cut"`
    means simple concatenation with no overlap; `mode="xfade"` means the
    two adjacent clips overlap by `duration_sec` using the named
    `xfade_transition` preset."""

    mode: str  # "hard_cut" | "xfade"
    xfade_transition: str | None = None
    duration_sec: float = 0.0


@dataclass(frozen=True)
class ExportSpec:
    """Mirrors packages/schemas/json/export_spec.schema.json."""

    format: str
    quality_preset: str
    video_bitrate_kbps: int | None = None
    audio_bitrate_kbps: int | None = None


@dataclass(frozen=True)
class ExportResult:
    output_uri: str
    format: str
    resolution: str
    fps: int
    duration_sec: float
    codec: str
