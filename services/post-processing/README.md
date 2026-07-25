# services/post-processing

## Post-Processing

**Responsibility:** Turns a project's per-shot RawClips into one
assembled master video: sequencing (Timeline Builder), transitions
(Transition Engine), audio mixing (Audio Pipeline), captions (Subtitle
System), thumbnails (Thumbnail Engine), and watermark/branding
(Watermark Engine) - composed by `FfmpegCompositor`, a real,
executable `IRenderCompositor` (`packages/video-composition-sdk`).

**Input:** A `Timeline` (`packages/schemas/json/timeline.schema.json`),
built from a project's `DirectorPlan` + per-shot video `AssetRecord`s.

**Output:** One assembled, mixed, subtitled/watermarked master video
file (handed to `services/export-service` for final format/quality
encoding).

**Consumed by:** Export Service

## Modules

| Module | Responsibility |
|---|---|
| `TimelineBuilder` | Sequences shots into a `Timeline`, honoring `Shot.transition_in`/`transition_out` (Phase 1's Shot Planner already decides these) |
| `TransitionEngine` + `transitions/` | Resolves a `Transition` into a `TransitionRecipe` via `config_sdk.TRANSITION_PLUGIN_REGISTRY` - 7 built-ins (`cinematic_cut`, `fade_in`, `fade_out`, `dissolve`, `match_cut`, `wipe`, `whip_pan`, `zoom`) plus custom plugin registration |
| `AudioPipeline` | Music/sfx/voiceover tracks, volume automation (piecewise-linear keyframes), builds the ffmpeg audio mix filtergraph |
| `SubtitleGenerator` | Auto-captions from shot descriptions or explicit cues; real SRT/WebVTT serializers; styling presets; multilingual (one `SubtitleTrack` per language); burn-in `force_style` |
| `ThumbnailEngine` | Real ffmpeg keyframe extraction - scene thumbnails (shot midpoint), auto/cover thumbnail |
| `WatermarkEngine` | Logo overlay (`Timeline.watermark`) + intro/outro (inserted as real `Timeline.video_clips`) |
| `FfmpegCompositor` | The one place ffmpeg filter syntax exists - `concat` for hard cuts, `xfade` for every other transition, `amix` for audio, `subtitles`(libass) for burn-in, `overlay` for the watermark |
| `PassthroughUpscaler` | The only concrete `IUpscaler` - copies input unchanged; see its docstring for why real upscaling isn't implemented here |

## Status (Phase 6)

Implemented and tested with **real ffmpeg subprocess execution**
against real synthetic clips (`tests/media_helpers.py`) - not mocked.
See `docs/adr/0012-post-production-pipeline.md`. Requires `ffmpeg`/
`ffprobe` on `PATH` (`docs/DEV_SETUP.md`). Wired into
`ProjectLifecycle.finalize_project` / `POST /projects/{id}/finalize`
via `PostProductionRunner` (`services/render-orchestrator`) as of
Phase 8 - see `docs/adr/0014-pipeline-integration.md`.
