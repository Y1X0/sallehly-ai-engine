# Iteration 0013: Single-tile decode also avoids NaN - but a real confound surfaced

**Kaggle run:** [30355470112](https://github.com/Y1X0/sallehly-ai-engine/actions/runs/30355470112), commit `8ba3653`
**Prompt:** `A cinematic sunset over a futuristic city, high quality` (unchanged since 0001)
**Params:** 480x272, 9 frames, 16fps, 20 steps, guidance_scale=6.0, seed=42, VAE tiling forced to a single tile (`tile_sample_min_height=608, tile_sample_min_width=1024`)

### 1. What was tested
Whether NaN-avoidance depends on calling `tiled_decode()` at all
(regardless of whether it actually splits into multiple tiles) versus
depending on genuinely splitting into >=2 tiles - by setting the tile
size larger than the actual 480x272 frame, forcing exactly one tile
through the same code path.

### 2. What failed / what was observed
**No NaN anywhere: 60/60 per-step tensor checks (latents,
prompt_embeds, negative_prompt_embeds x 20 steps) came back
`isnan: false`.** The latent-norm trajectory is remarkably close to
iteration 0012's real multi-tile run:
```
0012 (multi-tile):  261.85, 258.92, ..., 158.41, 165.34, 195.79
0013 (single-tile): 261.99, 258.92, ..., 158.65, 152.85, 157.57, 185.35
```
Nearly identical shape and magnitude - strong convergent evidence that
the underlying denoising process is doing essentially the same real
work in both cases.

`video.mp4`: 21,736 bytes (close to but distinct from 0012's 21,338 -
consistent with genuinely different, non-degenerate decoded content,
not an exact byte-for-byte repeat).

**A real confound, caught rather than glossed over:** this run's
logged `transformer_dtype`/`vae_dtype`/`text_encoder_dtype` are all
`torch.bfloat16` - not the `fp16` every prior iteration in this
investigation used (forced by `torch.cuda.is_bf16_supported()`
returning `False` on the T4 accelerator pinned since iteration
`ffe1e5b`). Iterations 0011/0012 predate the dtype-logging fields
added this iteration, so their actual dtype was never directly
confirmed - only assumed to be fp16 by the same T4-pinning logic. If
this run's Kaggle instance reported bf16 support (a different GPU
generation, or a driver/torch difference), **dtype itself is an
uncontrolled variable between 0012 and 0013**, not just tile count.

### 3. Root cause
**Tile-splitting count is not the deciding factor for NaN-avoidance** -
a single, unsplit tile (this iteration) avoids NaN just as reliably as
a real multi-tile split (iteration 0012). This points toward *calling
`tiled_decode()` at all* (vs. the non-tiled `decode()` path) as the
relevant factor, not the number of tiles produced.

**However, this conclusion is now weakened by the dtype confound**
above - it's not yet certain whether avoiding NaN is really about
`tiled_decode()` vs `decode()`, or partly/wholly attributable to
`bfloat16`'s wider exponent range (matching fp32's, unlike fp16)
happening to be active this run. This must be stated honestly rather
than claimed as fully isolated.

### 4. Evidence
- Per-step diagnostics: 0 occurrences of `isnan: true` or `isinf: true` across 60 checks (20 steps x 3 tensors).
- Latent-norm trajectory closely matching iteration 0012's real (multi-tile) run.
- `video.mp4`: 21,736 bytes - new, distinct size.
- Logged `transformer_dtype`/`vae_dtype`/`text_encoder_dtype`: all `bfloat16` - a genuine, newly-surfaced difference from this investigation's working assumption of `fp16` throughout.

### 5. What was changed
`pipeline.vae.enable_tiling(tile_sample_min_height=608,
tile_sample_min_width=1024, ...)` - forces a single-tile decode.
Confirmed: still avoids NaN, but the dtype confound means this alone
doesn't yet cleanly settle *why*.

### 6. Before vs after comparison
| Metric | 0012 (multi-tile, dtype unconfirmed) | 0013 (single-tile, bfloat16 confirmed) |
|---|---|---|
| NaN anywhere | none | none |
| Latent-norm trajectory | 261.85 -> 195.79 | 261.99 -> 185.35 (very similar shape) |
| video.mp4 size | 21,338 bytes | 21,736 bytes |
| Visible artifact (pending this iteration's visual check) | vertical blue banding (tile-blend seams) | not yet confirmed |
| Logged dtype | not captured (field added this iteration) | bfloat16 |

### 7. Benchmark scores
Not yet scored - pending visual confirmation of the actual frames
(same discipline as every prior iteration: finite numbers alone are
not sufficient evidence of real content).

### 8. Remaining weaknesses
- The dtype confound (bf16 vs fp16) between 0012 and 0013 needs
  resolving before claiming "single-tile decode alone fixes
  everything" - the real test would be forcing fp16 explicitly (or
  confirming which dtype 0012 actually used) and re-running with a
  single tile to isolate tile-count from dtype cleanly.
- Whether the vertical banding artifact from 0012 is actually gone
  (as predicted, since there's nothing to blend with one tile) is not
  yet confirmed visually.

### 9. Next experiment
Get the real video uploaded and inspected: run `eval/quality_metrics.py`
and directly view frames to check (a) whether the banding artifact is
gone and (b) whether real, recognizable content is finally present.
Separately, note for a future iteration: confirm whether the T4
accelerator pin is still being honored (this run's bf16 dtype suggests
it may not be, or that T4's bf16 support differs from what was
originally observed) and control for dtype explicitly in the next
tile-count comparison if the mechanism question needs fully settling.
