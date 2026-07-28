# Iteration 0013: Visual check reveals tile-blend seams; testing a single-tile decode

**Kaggle run:** pending (dispatched with this report)
**Prompt:** `A cinematic sunset over a futuristic city, high quality` (unchanged since 0001)
**Params:** 480x272, 9 frames, 16fps, 20 steps, guidance_scale=6.0, seed=42, VAE tiling with `tile_sample_min_height=608, tile_sample_min_width=1024` (both larger than the actual frame, forcing exactly one tile)

### 1. What was tested
Direct visual inspection of iteration 0012's real, user-uploaded video
(280x272 - correction, 480x272 - tiling ON, all-finite latents) to
check whether real, recognizable content is present now that the NaN
is resolved.

### 2. What failed / what was observed
`eval/quality_metrics.py`: avg_stddev 15.02 (still under the 20.0
flat-frame threshold, but qualitatively different from every prior
failure - blue-dominant color, mean_b up to 190 vs. the earlier
uniform brownish-gray, full 1-255 range on one channel in frame 1).

Direct visual inspection of 5 sampled frames: **a completely different
artifact from the checkerboard seen in iterations 0001-0007** - regular
vertical blue banding/stripes across the entire frame, no recognizable
scene (no sunset gradient, no city silhouette). Not random noise -
clean, periodic vertical bands, consistent across all sampled frames
with a subtle dot-texture visible near the frame edges.

### 3. Root cause
Confirmed by reading `AutoencoderKLWan.tiled_decode()`'s real source
directly (not guessed): the tile-splitting loop is `for j in range(0,
width, tile_latent_stride_width)`. With the default
`tile_sample_min_width=256` against our 480px-wide frame, this
produces exactly ~2 overlapping tiles (480/192-stride ≈ 2.5,
consistent with 2 real tile boundaries). The vertical banding matches
tile-blend seams along the width axis - a real, different failure
mode from the earlier checkerboard (which appeared at 960x544, where
more/smaller tiles relative to image size would produce a finer,
different-looking blend pattern).

**This means tiling is confirmed necessary for numerical stability
(iteration 0012) but its default tile-size configuration is
unsuitable for this small a frame - not a contradiction, two separate,
now-distinguished problems.**

### 4. Evidence
- `eval/quality_metrics.py` output: avg_stddev 15.02, mean RGB values wildly different (blue-dominant) from every prior iteration's brownish-gray - real, if artifact-laden, color variation.
- 5 sampled frames, directly viewed: consistent regular vertical banding, not noise, not the earlier checkerboard.
- `AutoencoderKLWan.tiled_decode()` source (installed diffusers package, quoted in code comments): confirms the tile loop's stride-based iteration count, directly explaining why a 480px-wide frame against `tile_sample_min_width=256`/`tile_sample_stride_width=192` produces a small number of tiles with visible blend boundaries.

### 5. What was changed
`pipeline.vae.enable_tiling()` now passes explicit
`tile_sample_min_height=608, tile_sample_min_width=1024` (and matching
strides) - both larger than any resolution tested so far (480x272 and
960x544) - forcing `tiled_decode()`'s own tile loop to produce exactly
one tile (no real splitting, no blending), while still calling
`tiled_decode()` rather than the non-tiled `decode()` path.

### 6-9. Pending
This report ships with the dispatch, matching this investigation's own
discipline (never claim results before they exist). Two possible
outcomes:
- If latents stay finite (no NaN) with a single, unsplit tile: this
  proves NaN-avoidance depends on *which function* is called
  (`tiled_decode` vs `decode`), not on genuinely splitting into >=2
  tiles - and this configuration (tiled code path, single real tile)
  should also remove the blend-seam artifact, since there's nothing
  to blend. This would be the actual fix.
- If NaN returns: numerical stability genuinely depends on real
  multi-tile splitting, not just which function is called - the next
  test would need to use a moderate tile size (larger than 256 but
  still smaller than 480/272, e.g. 320) to get real splitting with
  better-aligned boundaries instead of either extreme.
