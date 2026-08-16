# Iteration 0007: Root cause found - seed=0 was the degenerate input, not model precision

**Kaggle run:** [30338955244](https://github.com/Y1X0/sallehly-ai-engine/actions/runs/30338955244), commit `8e56e83`
**Prompt:** `A cinematic sunset over a futuristic city, high quality` (unchanged since 0001)
**Params:** 960x544, 17 frames, 16fps, 20 steps, guidance_scale=6.0, **seed=42 (was 0 in every prior iteration)**

### 1. What was tested
Whether the pipeline is sensitive to *any* input variation at all,
after 6 consecutive iterations (0001-0006) - covering fp16/fp32 VAE,
text encoder, transformer, and guidance_scale 1.0/6.0 - all produced
byte-for-byte identical output. Every prior iteration used the same
`seed=0`, never varied until now.

### 2. What failed / what was observed
**Definitive result: changing only the seed (0 -> 42) changed the
output.** `video.mp4` is **276,938 bytes - more than double the
127,355 bytes produced identically by every one of the 6 prior
iterations**, and no longer matches that byte count at all.

The new `step_latent_norms` diagnostic (added this iteration) shows
real, substantial, monotonic variation across the denoising steps:
```
693.28 -> 685.51 -> 677.02 -> 667.76 -> 657.62 -> 646.44 -> 634.13 ->
620.46 -> 605.15 -> 587.93 -> 568.48 -> 546.30 -> 521.16 -> 492.33 ->
459.18 -> 420.92 -> 377.97 -> 334.28 -> 306.05 -> 329.79
```
A 55.9% drop from step 1 to step 19 - the norm shrinking steadily as
the flow-matching process converges from pure noise toward a
structured sample, exactly the expected shape of a real, working
denoising trajectory. This is the first time this project has direct,
quantitative proof the model is doing genuine generative work.

### 3. Root cause
**`seed=0` specifically produced a degenerate, near-constant initial
state that the denoising process could not escape from, independent of
every precision fix and independent of guidance_scale/prompt
conditioning attempted in iterations 0001-0006.** This is not a bug in
this codebase's own code (the seed was passed and consumed correctly
throughout - `torch.Generator(device="cpu").manual_seed(resolved_seed)`
is standard, correct usage) - it is a property of how this specific
seed value interacts with this model/scheduler's initial-noise
sampling. This retroactively explains every piece of evidence gathered
across iterations 0001-0006 at once:
- Byte-identical output regardless of VAE/text-encoder/transformer
  precision: garbage in (a degenerate seed-0 starting point), garbage
  out, regardless of decode/encode precision.
- guidance_scale being a measured-real-compute but visually-no-op
  change: CFG combining two branches that both started from - and
  likely stayed close to - the same degenerate seed-0 initial state.
- Every previous "fix" (0002, 0003, 0005, 0006) was a reasonable,
  evidence-motivated hypothesis at the time, but none could have
  worked, because none touched the actual variable that mattered.

### 4. Evidence
- `video.mp4` byte count: 127,355 (0001-0006, all `seed=0`) vs.
  **276,938 (0007, `seed=42`)** - the first change in this number across
  7 iterations.
- `step_latent_norms`: real, substantial, monotonically-shaped
  variation (quoted above) - the first iteration where this trace
  isn't flat/degenerate.
- Kernel duration: 1136s - shorter than the other `guidance_scale=6.0`
  runs (1199-1314s), a real but secondary data point (not the focus of
  this iteration).
- Artifact zip size: 1,465,137 bytes vs. ~1.28-1.31M in prior
  iterations - consistent with genuinely higher-entropy (less
  compressible) real content, corroborating the byte-count finding
  independently.
- Direct pixel-level confirmation (frame extraction + visual
  inspection + `eval/quality_metrics.py`) is the mandatory next step
  before declaring this a full success - **not yet done**, per this
  project's own rule against declaring victory without visual
  evidence. Pending user upload (sandbox network policy blocks direct
  artifact download, as in every prior iteration).

### 5. What was changed
This iteration's own change was a workflow-dispatch input value only
(`seed: "42"` passed to an already-existing `--seed` CLI flag) - no
code logic changed. The `step_latent_norms`/`seed` input additions
that *enabled* this discovery shipped in the previous commit (`8e56e83`,
iteration 0006's report).

### 6. Before vs after comparison
| Metric | 0001-0006 (seed=0) | 0007 (seed=42) |
|---|---|---|
| video.mp4 size | 127,355 (identical x6) | **276,938** |
| step_latent_norms shape | not measured until 0006/0007 | real, monotonic 693->306 |
| Kernel duration | 947-1314s | 1136s |

### 7. Benchmark scores
Not yet scored - pending pixel-level verification of the actual visual
content (§4). A larger, more information-rich file is strong indirect
evidence of real content, but this project's own discipline requires
seeing the actual frames before scoring, exactly as done for every
prior (negative) iteration.

### 8. Remaining weaknesses
- Pixel-level confirmation is the single blocking item before this can
  be called a real fix rather than a promising signal.
- The *mechanism* of why `seed=0` specifically is degenerate for this
  model/scheduler is still not understood at the level of "why this
  exact value" - not investigated further here because it isn't
  necessary: the practical fix (never default to `seed=0`) is
  sufficient for the mission's actual goal (video quality), and
  chasing the exact numerical reason would be investigating a
  curiosity rather than improving output.

### 9. Next experiment
Pending pixel confirmation from the user's upload:
1. If confirmed real, recognizable content: change this engine's
   default seed away from `0` (in `infra/kaggle/dispatch_inference.py`
   and anywhere else defaulting to seed 0) so this degenerate case is
   never hit by default again, then begin running the full
   `eval/benchmark_prompts.yaml` suite category by category - the
   actual quality-improvement work this whole investigation was
   blocking.
2. If still degenerate on visual inspection despite the byte-count/
   latent-norm evidence: escalate to inspecting decoded frame
   statistics for this specific run directly (this report's evidence
   is strong but indirect - byte count and latent norms are proxies,
   not the ground truth `eval/quality_metrics.py` gives).

### 10. Correction (post-pixel-inspection)

The user uploaded the real video. `eval/quality_metrics.py` still
flagged it as flat (avg_stddev 12.46, improved from 9.21 but still
under the 20.0 threshold), and direct visual inspection of 5 sampled
frames confirmed it: **still the same class of contentless, textured
output as every prior iteration - no sunset, no city, no recognizable
scene - just a different color cast (warmer/tan vs the earlier
gray-brown) and a wider pixel range.**

This means §3's conclusion was wrong: `seed=0` was not a uniquely
degenerate input. Both `seed=0` and `seed=42` produce the same
fundamental defect - a real, measurable, seed-sensitive change in the
numbers (byte count, latent norms) is not the same thing as a fix, and
this report should have said "pending" more forcefully instead of
"likely fixed" before the visual check came back. See iteration 0008
for the corrected root-cause hypothesis (a checkerboard/tiling
artifact, found by zooming into these same frames) and what's actually
being tested next.
