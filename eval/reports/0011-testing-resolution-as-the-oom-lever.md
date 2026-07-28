# Iteration 0011: Resolution avoids the OOM but reveals a deeper problem - NaN latents

**Kaggle run:** [30352348205](https://github.com/Y1X0/sallehly-ai-engine/actions/runs/30352348205), commit `7dee188`
**Prompt:** `A cinematic sunset over a futuristic city, high quality` (unchanged since 0001)
**Params:** **480x272** (was 960x544), 9 frames, 16fps, 20 steps, guidance_scale=6.0, seed=42, VAE tiling disabled

### 1. What was tested
Whether halving resolution (960x544 -> 480x272) avoids the 13.45 GiB
VAE-decode OOM confirmed to be resolution-independent-of-frame-count
in iteration 0010, and - the real priority - whether disabling tiling
finally produces a non-checkerboarded, real decode now that OOM is out
of the way.

### 2. What failed / what was observed
**No OOM this time** - the job completed successfully. But the result
is far more diagnostic than "checkerboard or not":

```
"step_latent_norms": [NaN, NaN, NaN, NaN, NaN, NaN, NaN, NaN, NaN,
NaN, NaN, NaN, NaN, NaN, NaN, NaN, NaN, NaN, NaN, NaN]
```

**All 20 denoising steps produced NaN latents, from the very first
step.** `video.mp4` is only 1,859 bytes - consistent with NaN values
being clamped to some constant/degenerate pixel value during export,
producing a near-empty, maximally-compressible file (not real content,
not even the checkerboard texture seen in 0001-0007).

This is qualitatively different from every prior iteration's failure
mode. 0001-0007 (tiling enabled) produced real, non-NaN pixel data
(just checkerboarded/muddy). This iteration (tiling disabled, smaller
resolution/frame count) produced complete numerical failure.

### 3. Root cause
**Not yet isolated to one variable** - this run changed three things
at once relative to the last real success (iteration 0007): tiling
(on->off), resolution (960x544->480x272), and frame count (17->9).
Per the review of this investigation's own methodology (external
review received mid-investigation, prioritizing model-identity and
scheduler checks first): before assuming tiling is the differentiator,
model-loading code was directly re-audited:

- `build_real_pipeline()` calls `WanPipeline.from_pretrained(model_id,
  torch_dtype=pipeline_dtype)` exactly once - transformer, VAE, and
  text encoder all load from the same checkpoint in one atomic call.
  No manual mixing of components from different sources, no fallback
  path to a different model. This is identical between iteration 0007
  (real output) and iteration 0011 (NaN) - **ruling out "mismatched
  model versions" as the differentiator by direct code inspection**,
  not merely by assumption.
- No manual `scheduler=` override exists for the real (non-smoke)
  path - `FlowMatchEulerDiscreteScheduler()` is only manually
  constructed in `build_smoke_test_pipeline()` (the tiny CPU smoke
  test). The real pipeline uses whatever scheduler
  `from_pretrained()` loads from the checkpoint's own config - also
  identical between 0007 and 0011, **ruling out "wrong scheduler" as
  the differentiator** by the same direct code inspection.

This leaves tiling, resolution, and frame count as the three real
candidates, not yet disambiguated.

### 4. Evidence
- `step_latent_norms`: 20/20 NaN, first step included - not a
  late-onset instability, present from the start.
- `video.mp4`: 1,859 bytes (vs 127,355-276,938 in every prior
  successful-but-flawed iteration) - consistent with NaN, not with
  real or checkerboarded pixel data.
- Kernel duration: 612s - notably shorter than the 947-1314s range of
  every prior successful run, consistent with a smaller
  resolution/frame count reducing per-step compute, independent of the
  NaN question.
- Direct source-code re-audit of `build_real_pipeline()` (quoted
  above) confirms no model/scheduler mismatch is possible in this
  codebase's own code, for either the working (0007) or NaN (0011)
  configuration.

### 5. What was changed
This iteration's own change: resolution 960x544 -> 480x272 (workflow
input only, no code change). Confirmed: avoided the OOM, but revealed
a NaN problem that OOM had been masking (0008-0010 never got far
enough to log `step_latent_norms` at all - they crashed with OOM
*inside* the `pipeline()` call, before `generate_video()` could ever
reach its `return` statement, so this NaN failure mode may have been
present in all of 0008-0010 too, just invisible until now).

### 6. Before vs after comparison
| Metric | 0007 (960x544, 17f, tiling ON) | 0011 (480x272, 9f, tiling OFF) |
|---|---|---|
| step_latent_norms | real, 693->306 (monotonic) | **all NaN** |
| video.mp4 size | 276,938 bytes | 1,859 bytes |
| Visual content | Checkerboard/flat, no scene | not yet visually confirmed (NaN strongly predicts none) |
| Kernel duration | 1136s | 612s |

### 7. Benchmark scores
Not scored - NaN latents cannot produce meaningful content by
construction.

### 8. Remaining weaknesses
- The exact trigger for the NaN (tiling off vs. resolution vs. frame
  count, or an interaction between them) is not yet isolated - this is
  the single most important open question in the whole investigation.
- All of iterations 0008-0010's OOM crashes may have been hiding this
  same NaN failure the entire time (impossible to know retroactively -
  `generate_video()` never got to log anything before OOM killed the
  process).

### 9. Next experiment
Re-enable VAE tiling (only this one variable) at the *same* reduced
480x272/9-frame configuration this iteration used, keeping everything
else identical (seed=42, guidance_scale=6.0). If NaN disappears, tiling
itself is directly implicated as necessary for numerical stability at
this resolution (not just memory) - and the earlier
0001-0007 checkerboard vs. this iteration's NaN would both trace back
to the same underlying cause operating differently at different
scales. If NaN persists even with tiling back on, the resolution/frame
count change itself (not tiling) is the trigger, and the next test
isolates resolution from frame count directly.
