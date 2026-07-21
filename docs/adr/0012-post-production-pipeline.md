# ADR 0012: A real, ffmpeg-executable post-production pipeline

**Status:** Accepted

## Context

Phase 6 asks for a full post-production layer - clip/scene stitching,
a transition engine with a real plugin architecture, an audio pipeline
with volume automation, a subtitle system (SRT/VTT/burned-in/
multilingual), a thumbnail engine, multi-format/multi-preset export,
an upscaling interface, watermark/branding, and asset packaging into a
render manifest - "engine agnostic, provider agnostic, plugin
architecture, production-grade design."

Every previous "not-yet-executable" boundary in this codebase (Wan2.1
GPU inference, ADR 0010's Temporal test server) was real code that
genuinely could not run in this sandbox, honestly documented as such.
Post-production is different: `ffmpeg` is a real, installable system
binary (`apt-get install ffmpeg` - Ubuntu 24.04's package includes
libx264/libx265/libvpx/libopus/libmp3lame/libass, confirmed by
inspecting `ffmpeg -codecs`/`-filters` before building anything), so
this phase is held to a higher bar: every module that produces media
is exercised with **real ffmpeg subprocess execution** against real
synthetic clips, not mocked - `tests/media_helpers.py`'s
`make_color_clip`/`make_tone`/`sample_pixel` generate real lavfi test
sources and sample real rendered pixels/streams to verify correctness
(e.g. `test_burned_in_subtitles_render_visible_text` counts actual
yellow pixels in a decoded frame).

## Decisions

### 1. Two new packages, mirroring the generation-layer pattern exactly

`packages/video-composition-sdk` (`IRenderCompositor`,
`ITransitionPlugin`, `IUpscaler`, and dataclasses mirroring every new
schema) plays the same role for post-production that
`packages/video-engine-sdk` plays for generation (ADR 0001/0002): the
engine-agnostic contract layer neither `CreativeDirector` nor
`CreativeCompiler` nor `GenerationPipeline` ever imports.
`config_sdk.TRANSITION_PLUGIN_REGISTRY` reuses the exact same
`Registry` class `LLM_PROVIDER_REGISTRY`/`VIDEO_ENGINE_REGISTRY`/
`COMPUTE_PROVIDER_REGISTRY` already use - a real plugin architecture
(register a class, look it up by key), not a special case.

### 2. `FfmpegCompositor` is the one place ffmpeg syntax exists

`services/post-processing`'s `TimelineBuilder`, `AudioPipeline`,
`SubtitleGenerator`, and the Transition Engine's plugins all reason in
terms of schema-shaped dicts/dataclasses and, at most,
`TransitionRecipe` (an engine-agnostic "hard cut, or a named crossfade
of some duration" decision - see `video_composition_sdk.types`). Only
`FfmpegCompositor` (`compositor/ffmpeg_compositor.py`) turns any of
that into actual `-filter_complex` syntax. Swapping the concrete
compositor (a cloud rendering service, later) means implementing
`IRenderCompositor` again - nothing else in the pipeline changes.

### 3. A hard cut is `concat`, never a zero-duration `xfade`

Building `FfmpegCompositor`'s video filtergraph, `ffmpeg`'s `xfade`
filter was found (empirically, via direct CLI experiments before
writing any code) to have an edge case: an `offset` equal to the first
input's full duration collapses the output to roughly the first
input's length instead of the expected `offset + second_input_duration`.
Rather than working around that edge case, hard cuts use the `concat`
filter - not only does this sidestep the bug entirely, it's also the
semantically correct operation for a real cut. Every non-cut transition
(`dissolve`/`match_cut`/`wipe`/`whip_pan`/`zoom`) uses `xfade` with
`offset = cumulative_duration_so_far - overlap`, which is always
strictly less than the preceding clip's duration and never hits the
edge case.

### 4. `match_cut` and `whip_pan` are honest approximations, not simulations

A true match cut (matching action/composition across two shots) or
whip pan (a simulated fast camera swing) both need per-shot visual
alignment decided upstream - `packages/video-composition-sdk`'s
`Shot`/`CameraSetup` don't carry that information today, and inventing
it here would be overclaiming. `MatchCutPlugin` uses a very short plain
crossfade (reads as a cut, not a dissolve); `WhipPanPlugin` uses
ffmpeg's `hblur` xfade preset (the horizontal-motion-blur look a whip
pan reads as). Both plugin docstrings say exactly this - the same
honesty standard as `PassthroughUpscaler` (below) rather than a
believable-looking fake.

### 5. `IUpscaler`: prepared, not implemented - by explicit request

Real video upscaling (Real-ESRGAN-style) and frame interpolation
(RIFE-style) both need a GPU model deployment, the same class of
limitation as Wan2.1 inference (ADR 0010). Phase 6 explicitly asked to
"prepare interfaces for" these, not implement them.
`PassthroughUpscaler` (the only concrete `IUpscaler`) copies its input
unchanged - real, callable, testable, and honest about doing nothing
image-quality-wise, so the rest of the pipeline (Export Service quality
presets) can be built against the interface now.

### 6. Intro/outro become real Timeline clips; the logo overlay stays separate

`BrandingPackage` (`branding_package.schema.json`) has both
`logo_asset_id` (an overlay, applied throughout playback) and
`intro_asset_id`/`outro_asset_id` (full clips). `WatermarkEngine`
handles these very differently: `with_logo_overlay` sets
`Timeline.watermark`, which `FfmpegCompositor` interprets as an
`overlay` filter; `with_intro`/`with_outro` insert real `video_clips`
entries (`shot_id="branding_intro"`/`"branding_outro"`) at the start/end
of the Timeline, reusing the exact same `concat`/`xfade` machinery
every other clip transition uses rather than inventing a parallel
"branding clip" code path in `FfmpegCompositor`.

## Consequences

- `docs/DEV_SETUP.md` gains a new prerequisite: `ffmpeg` (with
  `-enable-libx264 -enable-libvpx -enable-libopus -enable-libass` at
  minimum) must be installed and on `PATH`.
  `post_processing.ffmpeg_utils.FfmpegNotAvailableError` is raised with
  a clear message (not a bare `FileNotFoundError`) if it isn't -
  checked in exactly one place (`ffmpeg_path()`/`ffprobe_path()`) every
  real filesystem/media operation in `services/post-processing` and
  `services/export-service` goes through.
- Every Phase 6 test that needs ffmpeg is marked
  `@pytest.mark.skipif(not FFMPEG_AVAILABLE, ...)` - the suite degrades
  gracefully (skips, doesn't fail) in an environment without ffmpeg
  installed, while running for real here.
- `services/post-processing`'s output (a composed master) and
  `services/export-service`'s output (a format/preset-encoded final
  file) are two distinct steps on purpose: composition (transitions,
  audio, subtitles, watermark) happens once; export (re-encoding to
  mp4/mov/webm at 720p-4k) can happen multiple times from the same
  master without recomposing.
- This pipeline is not yet wired into `ProjectLifecycle`/`apps/api`/
  `apps/web-dashboard` - Phase 6's scope (per the request that opened
  it) was the post-production modules and their tests, not lifecycle/
  API/frontend integration. That wiring (a `POST
  /projects/{id}/post-process` stage, a `PostProcessSpec` UI, ...) is
  the natural next phase, following the same pattern Phase 4 (pipeline)
  preceded Phase 5 (product layer on top of it).
