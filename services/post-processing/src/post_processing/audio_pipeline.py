from __future__ import annotations

import uuid
from typing import Any

import schemas


def _db_to_linear(db: float) -> float:
    return 10 ** (db / 20)


def _piecewise_volume_expr(base_db: float, automation: list[dict[str, float]]) -> str:
    """Builds an ffmpeg `volume` filter expression (eval=frame, `t` =
    seconds into the filtered stream) that linearly interpolates between
    `volume_automation` keyframes - holding the first keyframe's value
    before it and the last keyframe's value after it. Falls back to a
    constant multiplier when there's no automation."""
    if not automation:
        return f"{_db_to_linear(base_db):.6f}"

    keyframes = sorted(((kf["t"], kf["volume_db"]) for kf in automation), key=lambda kv: kv[0])
    expr = f"{_db_to_linear(keyframes[-1][1]):.6f}"
    for i in range(len(keyframes) - 1, 0, -1):
        t0, v0 = keyframes[i - 1]
        t1, v1 = keyframes[i]
        v0_lin, v1_lin = _db_to_linear(v0), _db_to_linear(v1)
        segment = f"({v0_lin:.6f}+({v1_lin:.6f}-{v0_lin:.6f})*(t-{t0:.6f})/{(t1 - t0):.6f})"
        expr = f"if(lt(t,{t1:.6f}),{segment},{expr})"
    first_t, first_v = keyframes[0]
    return f"if(lt(t,{first_t:.6f}),{_db_to_linear(first_v):.6f},{expr})"


class AudioPipeline:
    """Builds the audio side of a Timeline: adding music/sfx/voiceover
    tracks (each with volume, fade in/out, and optional volume-
    automation keyframes) and compiling them into a single ffmpeg
    filter_complex fragment that mixes every track down to one output
    stream (`amix`). Only produces the filtergraph fragment and its
    output label - FfmpegCompositor owns turning that into a full ffmpeg
    command (adding `-i` inputs, combining with the video filtergraph),
    keeping this class testable without invoking ffmpeg at all.
    """

    def add_track(
        self,
        timeline: dict[str, Any],
        kind: str,
        source_uri: str,
        start_time_sec: float = 0.0,
        duration_sec: float | None = None,
        volume_db: float = 0.0,
        fade_in_sec: float = 0.0,
        fade_out_sec: float = 0.0,
        volume_automation: list[dict[str, float]] | None = None,
        track_id: str | None = None,
    ) -> dict[str, Any]:
        """Returns a new Timeline dict with the track appended - does
        not mutate `timeline`. `kind` must be one of "music"/"sfx"/
        "voiceover" (timeline.schema.json)."""
        track: dict[str, Any] = {
            "track_id": track_id or f"audio_{uuid.uuid4().hex[:12]}",
            "kind": kind,
            "source_uri": source_uri,
            "start_time_sec": start_time_sec,
            "volume_db": volume_db,
            "fade_in_sec": fade_in_sec,
            "fade_out_sec": fade_out_sec,
        }
        if duration_sec is not None:
            track["duration_sec"] = duration_sec
        if volume_automation:
            track["volume_automation"] = volume_automation

        updated = dict(timeline)
        updated["audio_tracks"] = [*timeline.get("audio_tracks", []), track]
        schemas.validate(updated, "timeline")
        return updated

    def build_mix_filter(
        self, audio_tracks: list[dict[str, Any]], input_index_by_track_id: dict[str, int]
    ) -> tuple[str, str] | None:
        """`input_index_by_track_id` maps each track_id to the ffmpeg
        `-i` input index the compositor assigned its source_uri.
        Returns (filter_complex_fragment, output_label), or None if
        there are no audio tracks at all."""
        if not audio_tracks:
            return None

        chains: list[str] = []
        labels: list[str] = []
        for track in audio_tracks:
            idx = input_index_by_track_id[track["track_id"]]
            label = f"a{idx}"
            ops = [f"volume={_piecewise_volume_expr(track.get('volume_db', 0.0), track.get('volume_automation', []))}:eval=frame"]

            if track.get("fade_in_sec"):
                ops.append(f"afade=t=in:st=0:d={track['fade_in_sec']}")
            if track.get("fade_out_sec") and track.get("duration_sec"):
                fade_start = max(0.0, track["duration_sec"] - track["fade_out_sec"])
                ops.append(f"afade=t=out:st={fade_start}:d={track['fade_out_sec']}")

            delay_ms = round(track.get("start_time_sec", 0.0) * 1000)
            if delay_ms:
                ops.append(f"adelay={delay_ms}|{delay_ms}")

            chains.append(f"[{idx}:a]" + ",".join(ops) + f"[{label}]")
            labels.append(f"[{label}]")

        filter_complex = "".join(chains)
        if len(labels) > 1:
            filter_complex += "".join(labels) + f"amix=inputs={len(labels)}:duration=longest:normalize=0[aout]"
            return filter_complex, "aout"
        return filter_complex, labels[0].strip("[]")
