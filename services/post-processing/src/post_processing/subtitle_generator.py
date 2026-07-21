from __future__ import annotations

import uuid
from typing import Any

import schemas

# ASS/libass style presets (BGR hex, &H[AA]BBGGRR - see ffmpeg's `subtitles`
# filter `force_style` option) used when burning a SubtitleTrack in.
STYLE_PRESETS: dict[str, dict[str, Any]] = {
    "default": {
        "font_name": "Sans",
        "font_size": 24,
        "primary_color": "&H00FFFFFF",  # white
        "outline_color": "&H00000000",  # black outline
        "alignment": 2,  # bottom-center
    },
    "bold_yellow": {
        "font_name": "Sans",
        "font_size": 28,
        "primary_color": "&H0000FFFF",  # yellow
        "outline_color": "&H00000000",
        "alignment": 2,
        "bold": 1,
    },
    "cinematic": {
        "font_name": "Georgia",
        "font_size": 22,
        "primary_color": "&H00E6E6E6",  # near-white
        "outline_color": "&H00202020",
        "alignment": 2,
    },
}


class SubtitleGeneratorError(Exception):
    pass


class SubtitleGenerator:
    """Produces SubtitleTrack documents (subtitle_track.schema.json)
    either automatically from a DirectorPlan's shot descriptions (a
    deterministic default - real dialogue/voiceover transcription is a
    future upgrade, not implemented here) or from an explicit cue list
    (e.g. a voiceover script). Also serializes to real SRT/WebVTT and
    builds the ffmpeg burn-in filter fragment for a styling preset.
    """

    def generate_from_shots(
        self, director_plan: dict[str, Any], language: str = "en", style_preset_id: str = "default"
    ) -> dict[str, Any]:
        """One cue per shot, spanning that shot's duration, using its
        `description` as caption text - a reasonable default when no
        explicit dialogue/voiceover script is available."""
        cues: list[dict[str, Any]] = []
        t = 0.0
        for scene in sorted(director_plan["scenes"], key=lambda s: s["order"]):
            for shot in sorted(scene["shots"], key=lambda s: s["order"]):
                cues.append(
                    {
                        "cue_id": f"cue_{uuid.uuid4().hex[:12]}",
                        "start_sec": round(t, 3),
                        "end_sec": round(t + shot["duration_sec"], 3),
                        "text": shot["description"],
                        "shot_id": shot["shot_id"],
                    }
                )
                t += shot["duration_sec"]
        return self._build(director_plan["project_id"], language, cues, style_preset_id, burned_in=False)

    def generate_from_cues(
        self,
        project_id: str,
        language: str,
        cues: list[dict[str, Any]],
        style_preset_id: str = "default",
        burned_in: bool = False,
    ) -> dict[str, Any]:
        """`cues` items need at least start_sec/end_sec/text; cue_id is
        assigned if missing."""
        normalized = []
        for cue in cues:
            normalized_cue = dict(cue)
            normalized_cue.setdefault("cue_id", f"cue_{uuid.uuid4().hex[:12]}")
            normalized.append(normalized_cue)
        return self._build(project_id, language, normalized, style_preset_id, burned_in)

    def _build(
        self,
        project_id: str,
        language: str,
        cues: list[dict[str, Any]],
        style_preset_id: str,
        burned_in: bool,
    ) -> dict[str, Any]:
        if style_preset_id not in STYLE_PRESETS:
            raise SubtitleGeneratorError(
                f"Unknown style_preset_id '{style_preset_id}'. Available: {', '.join(sorted(STYLE_PRESETS))}"
            )
        track = {
            "track_id": f"sub_{uuid.uuid4().hex[:12]}",
            "project_id": project_id,
            "language": language,
            "style_preset_id": style_preset_id,
            "burned_in": burned_in,
            "cues": cues,
        }
        schemas.validate(track, "subtitle_track")
        return track

    def to_srt(self, subtitle_track: dict[str, Any]) -> str:
        blocks = []
        for index, cue in enumerate(subtitle_track["cues"], start=1):
            blocks.append(
                f"{index}\n"
                f"{_format_srt_time(cue['start_sec'])} --> {_format_srt_time(cue['end_sec'])}\n"
                f"{cue['text']}\n"
            )
        return "\n".join(blocks)

    def to_vtt(self, subtitle_track: dict[str, Any]) -> str:
        blocks = ["WEBVTT\n"]
        for index, cue in enumerate(subtitle_track["cues"], start=1):
            blocks.append(
                f"{index}\n"
                f"{_format_vtt_time(cue['start_sec'])} --> {_format_vtt_time(cue['end_sec'])}\n"
                f"{cue['text']}\n"
            )
        return "\n".join(blocks)

    def burn_in_force_style(self, style_preset_id: str) -> str:
        """The `force_style` value for ffmpeg's `subtitles` filter
        (libass), e.g. `FontName=Sans,FontSize=24,PrimaryColour=&H00FFFFFF,...`"""
        preset = STYLE_PRESETS.get(style_preset_id)
        if preset is None:
            raise SubtitleGeneratorError(
                f"Unknown style_preset_id '{style_preset_id}'. Available: {', '.join(sorted(STYLE_PRESETS))}"
            )
        field_map = {
            "font_name": "FontName",
            "font_size": "FontSize",
            "primary_color": "PrimaryColour",
            "outline_color": "OutlineColour",
            "alignment": "Alignment",
            "bold": "Bold",
        }
        return ",".join(f"{field_map[key]}={value}" for key, value in preset.items())


def _format_srt_time(seconds: float) -> str:
    total_ms = round(seconds * 1000)
    hours, rem_ms = divmod(total_ms, 3_600_000)
    minutes, rem_ms = divmod(rem_ms, 60_000)
    secs, ms = divmod(rem_ms, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def _format_vtt_time(seconds: float) -> str:
    total_ms = round(seconds * 1000)
    hours, rem_ms = divmod(total_ms, 3_600_000)
    minutes, rem_ms = divmod(rem_ms, 60_000)
    secs, ms = divmod(rem_ms, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{ms:03d}"
