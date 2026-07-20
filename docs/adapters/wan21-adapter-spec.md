# Wan2.1 Adapter Specification

Implements `IVideoEngine` (see `packages/video-engine-sdk`) for the
open-source [Wan2.1](https://github.com/Wan-Video/Wan2.1) model family
(Apache-2.0). Executable counterpart:
`services/video-engine-adapter/src/video_engine_adapter/adapters/wan21_adapter.py`.

## 1. Why Wan2.1 as the first engine

- Supports text-to-video, image-to-video, and video editing — covers the
  full brief-to-clip range this platform needs from day one.
- Runs on consumer/prosumer GPUs (the smaller checkpoint variants),
  keeping RunPod/Vast.ai rental cost low during Phase 0-3.
- Apache-2.0 licensed — compatible with commercial use; tracked
  explicitly in `models/registry.yaml`.

## 2. Capability manifest (declared value, `Wan21Adapter.capabilities()`)

| Field | Value | Notes |
|---|---|---|
| `modes` | `text_to_video`, `image_to_video`, `video_edit` | |
| `max_shot_duration_sec` | `5.0` | Native Wan2.1 output is short clips; longer scenes are achieved by the Shot Planner emitting more shots, not by asking the engine for a longer single clip |
| `resolutions` | `832x480`, `1280x720` | Matches the officially released checkpoints' trained resolutions |
| `fps_options` | `16`, `24` | |
| `motion_strength_range` | `0-100` (normalized) | Rescaled internally to whatever Wan2.1's actual sampler-level motion parameter turns out to be — see open question #2 |
| `supports_conditioning_images` | `true`, max `1` | For `image_to_video` |
| `min_vram_gb` | `24` | Assumes a mid-size checkpoint (see open question #1); the 14B checkpoint needs meaningfully more |
| `license` | `Apache-2.0` | |

These values seed `models/wan2.1/capability_manifest.yaml`, the file the
Render Configuration Compiler actually reads at runtime — this table and
that file must be kept in sync.

## 3. RenderSpec -> Wan2.1 native payload mapping

| `RenderSpec` field | Wan2.1 native field | Transform |
|---|---|---|
| `positive_prompt` | `prompt` | passthrough |
| `negative_prompt` | `negative_prompt` | passthrough, empty string if unset |
| `resolution` ("832x480") | `width`, `height` | split on "x" |
| `duration_sec`, `fps` | `num_frames` | `round(duration_sec * fps)` |
| `fps` | `fps` | passthrough |
| `seed` | `seed` | passthrough |
| `motion_strength` (0-100) | *(engine-native motion param)* | rescale from the 0-100 normalized range into whatever Wan2.1 actually exposes — open question #2 |
| `conditioning_images` | `image` / `input_image` | first entry only (manifest caps at 1) |
| `mode` | `task` | `text_to_video->t2v`, `image_to_video->i2v`, `video_edit->v2v` |
| `quality_tier` | `sampling_steps` | `"final" -> 40`, `"preview" -> 15` (cheap/fast storyboard-stage preview vs full-cost final render, see `render_configuration.schema.json`) |

Fields intentionally **not** mapped from any shared schema: anything
Wan2.1-specific that no other engine would understand (e.g. a
checkpoint-specific guidance-scale tuning knob) is hardcoded inside this
adapter, never added to `render_configuration.schema.json`.

## 4. Execution container contract

`workers/gpu-worker` is the container `EngineJobPayload.container_image`
points to (`sallehly/wan21-worker:2.1.0`). Its `handler.py`:

1. Loads Wan2.1 once at process start, kept resident across invocations
   (both RunPod Serverless "warm" workers and a persistent Vast.ai
   job-runner process satisfy this).
2. Receives the `input` dict built by `build_job_payload`.
3. Runs inference, uploads the resulting clip to the configured bucket.
4. Returns `{"output_uri": ..., "engine_metadata": {...}}`, which
   `IComputeProvider.fetch_output` turns into an `EngineJobOutput` and
   `Wan21Adapter.parse_result` turns into a `RawClip`.

## 5. Open questions for Phase 3 implementation

1. **Checkpoint size:** Wan2.1 ships multiple sizes (e.g. a ~1.3B model
   that fits comfortably in 24GB VRAM, and a larger ~14B model for higher
   fidelity that needs significantly more). Start with the smaller
   checkpoint to keep RunPod/Vast.ai rental cost down; revisit once
   quality feedback from real storyboards comes in.
2. **Exact motion-strength control:** confirm Wan2.1's actual exposed
   parameter for motion intensity (may be an implicit function of guidance
   scale / sampler settings rather than a single named argument) and
   finalize the rescale function in `Wan21Adapter.build_job_payload`.
3. **Video-edit mode specifics:** `video_edit` (editing an existing clip)
   has different input requirements than `t2v`/`i2v`; the payload mapping
   above covers only `t2v`/`i2v` in detail and needs a dedicated pass once
   a Shot Planner use case requires it.

## 6. What replacing Wan2.1 later actually involves

Per ADR 0001, a future custom foundation model needs only:

1. A new class implementing `IVideoEngine` (own `capabilities()`,
   `build_job_payload()`, `parse_result()`).
2. A new `capability_manifest.yaml` entry in `models/`.
3. A new entry in `models/registry.yaml`.
4. `VIDEO_ENGINE=<new-engine-id>` in config.

No change to any Planner, the Render Configuration Compiler, the Render
Orchestrator's control flow, or any `IComputeProvider` implementation.
