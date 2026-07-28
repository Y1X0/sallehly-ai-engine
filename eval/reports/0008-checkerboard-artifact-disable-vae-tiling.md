# Iteration 0008: Checkerboard artifact identified - disable VAE tiling

**Kaggle run:** pending (this report ships with the code change, dispatched next)
**Prompt:** `A cinematic sunset over a futuristic city, high quality` (unchanged since 0001)
**Params:** 960x544, 17 frames, 16fps, 20 steps, guidance_scale=6.0, seed=42 - single-variable change: `pipeline.vae.enable_tiling()` removed (kept `enable_slicing()`)

### 1. What was tested
Direct visual re-inspection of iteration 0007's user-uploaded video
(seed=42), since `eval/quality_metrics.py` still flagged it as flat
(avg_stddev 12.46, improved from 9.21 but still under the 20.0
threshold) despite the byte-count/latent-norm evidence looking
promising.

### 2. What failed / what was observed
5 sampled frames, visually inspected directly, all show the same
contentless, textured output as every prior iteration - no sunset, no
city, no recognizable scene - just a warmer color cast and wider pixel
range than iteration 0001-0006's output. **Zooming into a 200x200px
crop of frame 1 revealed the texture clearly: a clean, regular,
uniform-scale checkerboard/basket-weave pattern - not random noise.**
This is a well-documented artifact signature (deconvolution/tiling
checkerboard artifacts), not the appearance of degraded-but-real
content.

### 3. Root cause
**`pipeline.vae.enable_tiling()`** - enabled in iteration 0002 (commit
`d2e26d8`) to fix a real `OutOfMemoryError` ("Tried to allocate
13.45 GiB") - has been active in every single real Kaggle run since,
across all 7 iterations of this investigation (0002-0007), regardless
of precision, guidance_scale, or seed. VAE tiling splits the decode
into overlapping spatial tiles and blends them back together; if the
tile size/overlap doesn't align cleanly with this specific VAE's
latent-space downsampling factor, the blend introduces exactly this
kind of regular, fine-grained checkerboard pattern across the entire
image - consistent with why every iteration so far, regardless of
what else was changed, produced the same *class* of artifact (only
its color/brightness varied with precision/seed changes, never its
fundamental checkerboard character).

This is a stronger, more mechanistically specific explanation than any
prior hypothesis in this investigation, and directly explains why
seed=42 (iteration 0007) genuinely changed the numbers (byte count,
latent norms) without fixing the actual defect: changing the seed
changes what the model tries to generate underneath, but the VAE
tiling artifact stamps its own texture on top of *whatever* comes out,
regardless of seed.

### 4. Evidence
- `eval/quality_metrics.py` on iteration 0007's video: avg_stddev 12.46, still flagged flat despite the byte-count improvement.
- Direct visual inspection of 5 sampled frames (0007's video) - all show the same textured, contentless appearance.
- A 200x200px zoomed crop of frame 1 (upscaled with nearest-neighbor to preserve the exact pixel pattern) shows a clean, regular checkerboard/basket-weave texture at a small, uniform scale across the whole crop - visually distinct from random noise, matching the documented signature of tiled-decode blending artifacts.
- `enable_tiling()` was introduced in commit `d2e26d8` (iteration 0002's report) and has been present, unquestioned, in every real run since - a 7-iteration blind spot in this investigation, since every prior hypothesis (VAE dtype, text-encoder dtype, transformer dtype, guidance_scale, seed) tested something *other* than the tiling mechanism itself.

### 5. What was changed
Removed `pipeline.vae.enable_tiling()`, kept `pipeline.vae.enable_slicing()`
(slicing splits along the batch/frame dimension, not spatially, and
isn't implicated in a spatial checkerboard the way tile blending is).

### 6. Before vs after comparison
| Metric | 0007 (tiling enabled) | 0008 (tiling disabled) |
|---|---|---|
| Visual content | Checkerboard/textured, no scene | pending |
| avg_stddev | 12.46 | pending |
| OOM risk | none (tiling was masking the earlier OOM) | real - this is the exact mitigation that fixed the 13.45GiB failure |

### 7. Benchmark scores
Not yet scored - pending this iteration's real Kaggle run.

### 8. Remaining weaknesses
- If disabling tiling reintroduces the OOM, a different memory
  mitigation is needed (lower resolution/frame count, or investigating
  `tile_sample_min_size`/`tile_overlap_factor` parameters instead of
  disabling tiling outright) - itself a useful, diagnostic outcome,
  not a wasted iteration.
- If tiling wasn't actually the cause, the checkerboard pattern must be
  investigated elsewhere (e.g. the transformer's own patchify/
  unpatchify step, or an upsampling layer inside the VAE decoder
  itself, independent of tiling).

### 9. Next experiment
Run with tiling disabled. If real recognizable content appears (no
OOM, no checkerboard), begin the actual quality-improvement work this
investigation was blocking: run `eval/benchmark_prompts.yaml`
category by category. If OOM occurs, the next single change is a
memory mitigation that doesn't touch the VAE's spatial decode (e.g.
reducing `num_frames`/resolution for now, revisiting tiling parameters
later). If output is still checkerboarded with tiling off, investigate
the transformer's patchify/unpatchify path directly.
