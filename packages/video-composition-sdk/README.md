# packages/video-composition-sdk

Engine-agnostic contracts for post-production, mirroring
`packages/video-engine-sdk`'s role for generation (ADR 0001/0002):

| Interface | Role | Concrete implementation |
|---|---|---|
| `IRenderCompositor` | Turns a `Timeline` into one assembled master video file | `FfmpegCompositor` (`services/post-processing`) |
| `ITransitionPlugin` | Resolves a `Transition` into a `TransitionRecipe` (hard cut, or a named crossfade of some duration) | built-in plugins in `services/post-processing/transitions/`, registered in `config_sdk.registry.TRANSITION_PLUGIN_REGISTRY` |
| `IUpscaler` | Prepared interface for video upscaling/frame interpolation/quality enhancement | `PassthroughUpscaler` (`services/post-processing`) - not real upscaling, see docstring |

## Types

`types.py` mirrors the corresponding JSON Schemas exactly (same
dict-in-the-pipeline / dataclass-at-the-boundary pattern as
`video_engine_sdk.types` - see ADR 0009):

| Dataclass | Schema |
|---|---|
| `Timeline`, `VideoClip`, `AudioTrack` | `packages/schemas/json/timeline.schema.json` |
| `Transition` | `packages/schemas/json/transition.schema.json` |
| `BrandingPackage` | `packages/schemas/json/branding_package.schema.json` |
| `SubtitleTrack`, `SubtitleCue` | `packages/schemas/json/subtitle_track.schema.json` |
| `ExportSpec` | `packages/schemas/json/export_spec.schema.json` |

`TransitionRecipe`, `CompositionResult`, and `ExportResult` have no JSON
Schema - they're return values, not cross-service contracts.

## Why a separate package from video-engine-sdk

Generation (`IVideoEngine`/`IComputeProvider`) and post-production
(`IRenderCompositor`/`ITransitionPlugin`) are independent axes of
change - swapping the video-generation model has nothing to do with
swapping the compositor, and vice versa. Keeping them in separate
packages means a post-production-only change never touches, or even
imports, anything generation-related, and `CreativeDirector`/
`CreativeCompiler`/`GenerationPipeline` stay entirely unaware this
package exists - the same boundary discipline as ADR 0001.
