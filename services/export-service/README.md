# services/export-service

## Export System

**Responsibility:** Produces final delivery artifacts from the
assembled master video (`services/post-processing`'s output): a real
ffmpeg re-encode to the requested container format and quality preset
(`ExportService`), and bundling the export + thumbnails + subtitle
files into one `RenderManifest` (`AssetPackager`) - the single record
handed to a caller as "the finished thing" for a project.

**Input:** Assembled master video URI from Post-Processing +
`ExportSpec` (`packages/schemas/json/export_spec.schema.json`).

**Output:** A final video `AssetRecord` (project-level, `kind="video"`)
plus a schema-valid `RenderManifest`
(`packages/schemas/json/render_manifest.schema.json`).

**Consumed by:** Frontend / API caller

## Formats and quality presets

| Format | Video codec | Audio codec |
|---|---|---|
| `mp4` | `libx264` | `aac` |
| `mov` | `libx264` | `aac` |
| `webm` | `libvpx-vp9` | `libopus` |

| Preset | Resolution |
|---|---|
| `720p` | 1280x720 |
| `1080p` | 1920x1080 |
| `1440p` | 2560x1440 |
| `4k` | 3840x2160 |

Bitrates default per preset (`quality_presets.py`) and can be
overridden explicitly in `ExportSpec`.

## Status (Phase 6)

Implemented and tested with **real ffmpeg subprocess execution**
against real synthetic clips - every format/preset combination is
actually encoded and verified via `ffprobe`, not mocked. See
`docs/adr/0012-post-production-pipeline.md`. Requires `ffmpeg`/
`ffprobe` on `PATH` (`docs/DEV_SETUP.md`); not yet wired into
`ProjectLifecycle`/`apps/api`.
