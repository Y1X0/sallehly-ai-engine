# Iteration 0011: Testing resolution (not frame count) as the OOM lever

**Kaggle run:** pending (dispatched with this report)
**Prompt:** `A cinematic sunset over a futuristic city, high quality` (unchanged since 0001)
**Params:** **480x272** (was 960x544), 9 frames, 16fps, 20 steps, guidance_scale=6.0, seed=42, VAE tiling disabled

### 1. What was tested
Whether the fixed 13.45 GiB VAE-decode OOM (identical at both 17 and 9
frames - iteration 0010) is resolution-dependent rather than
frame-count-dependent, by halving both width and height (a diagnostic
deviation from `models/wan2.2-ti2v-5b/capability_manifest.yaml`'s only
documented supported resolution, 960x544 - used here only to isolate
the variable, not as a proposed permanent change).

A second, related correction to this investigation's own reasoning:
iterations 0008-0010 assumed disabling VAE tiling would remove the
checkerboard artifact seen in 0001-0007, but **neither non-tiled
attempt ever produced a video** (both OOM'd) - so that hypothesis was
never actually confirmed, only assumed. The checkerboard's very fine,
uniform granularity (visible in the zoomed crop from 0007/0008) is
also more consistent with a classic deconvolution/upsampling
checkerboard artifact (a well-documented failure mode tied to
transposed-convolution stride/kernel mismatches, appearing uniformly
across the whole decoded image) than with tile-boundary blending seams
(which would appear as discontinuities at the tile stride's specific
periodic interval - 192px per `AutoencoderKLWan`'s own defaults
`tile_sample_min_height/width=256`, `tile_sample_stride_height/width=192`
- not a fine sub-10px texture). This iteration's real priority is
getting *any* successful non-tiled decode to directly observe whether
the checkerboard persists, which would settle that open question with
real evidence instead of an assumption.

### 2-9. Pending
This report is filed with the dispatch, matching this investigation's
own discipline (never claim results before they exist). Will be
updated with the real outcome once this run completes.
