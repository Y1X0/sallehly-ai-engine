# Iteration 0006: transformer fp32 upcast (last remaining fp16 submodule)

**Kaggle run:** [30336718604](https://github.com/Y1X0/sallehly-ai-engine/actions/runs/30336718604), commit `89aa62f`
**Prompt:** `A cinematic sunset over a futuristic city, high quality` (unchanged since 0001)
**Params:** 960x544, 17 frames, 16fps, 20 steps, guidance_scale=6.0, seed=0 - single-variable change: `pipeline.transformer` (and `transformer_2` if present) upcast to fp32

### 1. What was tested
Whether `WanTransformer3DModel` (5B params) overflowing in fp16 is the
root cause of the flat/degenerate output, having already ruled out the
VAE (0002) and text encoder (0005) individually.

### 2. What failed / what was observed
Job succeeded with **no OOM** (a real, informative negative result on
its own - the T4 had enough headroom for a full-fp32 transformer under
sequential offload). Duration was 1314s - in the same range as the
other `guidance_scale=6.0` runs (1199s/1311s/1260s), not meaningfully
different (expected: this change affects numerical precision, not the
number of forward passes).

`video.mp4` is **still exactly 127,355 bytes - the 6th consecutive
identical result** (iterations 0001-0006, spanning fp16 VAE, fp32 VAE,
guidance_scale 1.0 and 6.0, fp32 text encoder, and now fp32
transformer, have all produced the exact same byte count).
`metadata.json` again confirms correct wiring
(`"guidance_scale": 6.0`, correct prompt).

### 3. Root cause
**All three model submodules (VAE, text encoder, transformer) are now
individually confirmed, by direct isolated testing, to have zero
effect on the degenerate output when upcast to fp32.** This
conclusively rules out fp16 numerical overflow anywhere in the model
as the cause - the root cause is not a precision problem at all.

Given a real, measured compute-time increase whenever
`guidance_scale > 1.0` (proving the extra CFG forward pass genuinely
executes) combined with a completely unchanged final output, the most
parsimonious remaining explanation is that **the actual denoising
loop's effect on `latents` is negligible** - i.e. the final video is
dominated by the initial random noise (always generated from the same
`seed=0` in every iteration so far, never varied), regardless of what
`noise_pred` the model computes at each step. This has not been tested
directly until this iteration's follow-up change (see §5/§9) - every
prior report's hypothesis concerned model precision; this is the first
to question the denoising loop's actual effect.

### 4. Evidence
- `metadata.json`: `"prompt": "A cinematic sunset over a futuristic city, high quality", "guidance_scale": 6.0` - wiring confirmed correct again.
- `video.mp4`: 127,355 bytes - 6th consecutive identical occurrence.
- No OOM despite fp32 transformer - real evidence the T4 has memory headroom for this, ruling out "the fix couldn't even run" as an explanation.
- Kernel duration 1314s, consistent with other `guidance_scale=6.0` runs - confirms this change didn't alter the loop's execution count or structure, only numerical precision.
- Note: an attempted fast, free, local reproduction of the "does
  conditioning affect output" question via this repo's own real (tiny,
  CPU, no-GPU-needed) `build_smoke_test_pipeline()` was inconclusive -
  its randomly-initialized weights have never learned any relationship
  between text conditioning and output, so a null result there proves
  nothing about the real, trained model. This is recorded honestly as
  an attempted-but-invalid experiment, not evidence either way.

### 5. What was changed
This iteration's own change (evaluated above): `pipeline.transformer`/
`transformer_2` upcast to fp32, commit `89aa62f`. Confirmed to have had
no measurable effect - completing the elimination of every fp16
submodule.

Additionally, this report is accompanied by two further changes
(commit after this report) needed to test the next hypothesis, since
this project's evidence-based process requires a real fact, not
another guess: a `callback_on_step_end` hook logging each denoising
step's `latents` L2 norm (`step_latent_norms`, added to
`generate_video()`'s returned metadata) and a configurable `seed`
input on the Kaggle workflow (every run so far used the same,
never-varied `seed=0`).

### 6. Before vs after comparison
| Metric | 0005 (text_encoder fp32) | 0006 (transformer fp32) |
|---|---|---|
| video.mp4 size | 127,355 | 127,355 (identical) |
| Kernel duration | 1260s | 1314s (within noise) |
| OOM? | No | No |
| guidance_scale/prompt wiring | confirmed correct | confirmed correct |

### 7. Benchmark scores
Unchanged from all prior iterations (0/10 overall) - 6 consecutive
iterations with zero output change.

### 8. Remaining weaknesses
- Root cause still not confirmed. All three fp16-precision hypotheses
  are now exhausted; the investigation must move to the denoising
  loop's actual per-step effect and to whether the pipeline responds
  to *any* input variation (including the seed, never varied before).

### 9. Next experiment
Two changes ship together with this report (both purely diagnostic /
input-variation, not another blind "fix"):
1. `step_latent_norms` in `generate_video()`'s metadata - a real
   per-step trace of `latents`' L2 norm via diffusers' own official
   `callback_on_step_end` hook. A flat/near-constant trace directly
   proves the denoising loop isn't meaningfully updating `latents`
   regardless of anything else tested so far.
2. A configurable `seed` input on the Kaggle workflow (previously
   hardcoded to the default of 0 in every run) - the next dispatch
   will use a genuinely different seed to test whether the pipeline is
   sensitive to *any* input variation at all, the most fundamental
   remaining question after 6 consecutive identical results.
