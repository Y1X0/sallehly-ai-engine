# Iteration 0012: Clean A/B confirms tiling prevents the NaN (not just OOM)

**Kaggle run:** [30353811714](https://github.com/Y1X0/sallehly-ai-engine/actions/runs/30353811714), commit `52a17e7`
**Prompt:** `A cinematic sunset over a futuristic city, high quality` (unchanged since 0001)
**Params:** 480x272, 9 frames, 16fps, 20 steps, guidance_scale=6.0, seed=42, **VAE tiling re-enabled** (only variable changed from iteration 0011)

### 1. What was tested
Whether re-enabling VAE tiling, at the *exact same* reduced
480x272/9-frame configuration that produced all-NaN latents in
iteration 0011 (changing only this one variable), removes the NaN.

### 2. What failed / what was observed
**Clean, decisive result: no NaN.** `step_latent_norms`:
```
261.85, 258.92, 255.74, 252.28, 248.52, 244.39, 239.88, 234.94,
229.48, 223.40, 216.70, 209.19, 200.87, 191.74, 181.94, 171.84,
162.96, 158.41, 165.34, 195.79
```
Real, finite numbers throughout - mostly a steady monotonic decrease
(consistent with normal flow-matching convergence), with a mild
uptick in the last two steps (158 -> 165 -> 196) that is not itself
alarming (still finite, no NaN/Inf) but worth keeping in view as a
secondary signal, not over-interpreted on its own.

`video.mp4`: 21,338 bytes - a new, distinct byte count from every
prior iteration (127,355 / 276,938 / 1,859), consistent with genuinely
different (and non-degenerate, non-NaN-clamped) content. Kernel
duration: 675s.

### 3. Root cause
**Confirmed by direct, single-variable A/B comparison (not inferred):**
tiling ON vs. OFF is the exact and only difference between this run
and iteration 0011, at identical resolution, frame count, seed, and
guidance_scale. Tiling ON -> finite latents; tiling OFF -> all-NaN
latents, from the first step. This directly implicates VAE tiling as
necessary for numerical stability at this configuration - not merely a
memory-saving convenience, as it was originally introduced for in
iteration 0002.

**Explicitly not over-claimed here, per this investigation's own
discipline:** this does not yet prove *why* tiling prevents the NaN
(e.g. whether it changes an internal dtype cast, avoids a specific
large intermediate tensor that would otherwise overflow, or changes
which code path/kernel gets used) - only that it does, empirically,
at this exact configuration. The mechanism remains open; the practical
fact (tiling must stay on) is what's actionable right now.

### 4. Evidence
- `step_latent_norms`: 20/20 finite values (quoted above) vs.
  iteration 0011's 20/20 NaN - identical config otherwise.
- `video.mp4`: 21,338 bytes, a new distinct size, consistent with real
  (non-NaN-clamped) content.
- Single-variable change from iteration 0011: only
  `pipeline.vae.enable_tiling()` was re-added; resolution (480x272),
  frame count (9), seed (42), guidance_scale (6.0), and prompt were
  all held constant.

### 5. What was changed
Re-enabled `pipeline.vae.enable_tiling()` (undoing iteration 0008's
removal), keeping the reduced 480x272/9-frame configuration from
iteration 0011.

### 6. Before vs after comparison
| Metric | 0011 (480x272, tiling OFF) | 0012 (480x272, tiling ON) |
|---|---|---|
| step_latent_norms | all NaN | all finite, 261.85 -> 195.79 |
| video.mp4 size | 1,859 bytes | 21,338 bytes |
| Kernel duration | 612s | 675s |

### 7. Benchmark scores
Not yet scored - pending visual confirmation of the actual video
content (numbers being finite is necessary but not sufficient
evidence of real, recognizable content - this investigation has
already been burned once, in iteration 0007, by treating improved
numbers as a proxy for a real fix without checking frames directly).

### 8. Remaining weaknesses
- The mechanism behind *why* tiling prevents the NaN is still unknown
  - only the empirical fact is established.
- Whether real, recognizable content (vs. another visual artifact like
  the earlier checkerboard) is present at this smaller resolution is
  not yet confirmed - needs the actual frames inspected directly.
- The mild late-step latent-norm uptick (158 -> 165 -> 196) is
  unexplained and worth watching in future iterations, though not
  treated as urgent given it stayed finite.

### 9. Next experiment
Get the real video uploaded and inspected directly: run
`eval/quality_metrics.py`, then extract and zoom into frames exactly
as done for iterations 0007/0008, to check specifically whether real,
recognizable content is present now, or whether a different visual
defect (the earlier checkerboard, or something else) remains despite
the numerical stability fix. This is the actual decisive test - finite
numbers alone were already shown (iteration 0007) to be an unreliable
proxy for real content on their own.
