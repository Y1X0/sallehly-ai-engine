# Iteration 0022: Baseline quality validation - 4 real videos after the transformers==4.48.0 fix

**Kaggle runs:** A [30440159420](https://github.com/Y1X0/sallehly-ai-engine/actions/runs/30440159420), B [30441514431](https://github.com/Y1X0/sallehly-ai-engine/actions/runs/30441514431), C [30442724517](https://github.com/Y1X0/sallehly-ai-engine/actions/runs/30442724517), D [30444564540](https://github.com/Y1X0/sallehly-ai-engine/actions/runs/30444564540), all on commit `4482b7e`
**Shared config:** `480x272`, `9` frames, `16fps`, `20` sampling steps, `guidance_scale=6.0` (engine default), `seed=42`, `enable_sequential_cpu_offload` ON, `transformers==4.48.0` (force-installed per eval/reports/0021's fix), `diffusers==0.37.1`, `torch==2.10.0+cu128`, `pipeline_dtype=torch.bfloat16`, GPU `Tesla T4`.

This is the first quality validation run since the root-cause fix (eval/reports/0016-0021: `transformers==5.0.0` produced an exact all-zero UMT5 text-conditioning tensor; `transformers==4.48.0` produces real embeddings). Every iteration before 0021 that reached this point (0001-0020) produced flat/muddy, prompt-independent output - this is the first time this pipeline has been evaluated with real text conditioning flowing through it.

### 1. What was tested

Four distinct prompts, same config otherwise, to check whether: (a) the fix holds inside a full, real `WanPipeline` generation (not just the isolated encoder test from 0021), (b) different prompts now produce genuinely different embeddings/output (unlike the old all-zero era, where every prompt produced byte-identical video), and (c) the resulting video content visually matches its prompt.

| | Prompt |
|---|---|
| A | "A red sports car driving through a futuristic city at night, cinematic lighting" |
| B | "A modern white house surrounded by mountains during sunrise, cinematic drone shot" |
| C | "A snowy mountain landscape at sunrise, realistic documentary style" |
| D | "A humanoid robot walking in a futuristic city, cinematic movie scene" |

### 2. Results table

| | `prompt_embeds_norm` | `negative_prompt_embeds_norm` | Video size | `avg_stddev` | `flat_frame_suspected` | Generation time |
|---|---|---|---|---|---|---|
| A | 17.77 | 1.643 | 43,432 bytes | 77.78 | false | ~14 min |
| B | 18.94 | 1.643 | 35,182 bytes | 89.76 | false | ~14 min |
| C | 17.16 | 1.643 | 54,027 bytes | 80.23 | false | ~15.5 min |
| D | 18.91 | 1.643 | 55,621 bytes | 70.97 | false | ~13.5 min |

`negative_prompt_embeds_norm` is identical across all four because the negative prompt is always the empty string (`""`, this engine's default) - only the positive-prompt embedding is expected to vary, and it does: `17.16-18.94`, a real, prompt-dependent spread, not the constant `0.0` every prior iteration measured. Video byte sizes also differ meaningfully (35KB-56KB) - under the old all-zero-embedding bug, every prompt produced byte-for-byte identical output regardless of content (eval/reports/0007, 0015).

`quality_metrics.py`'s flat-frame threshold is `avg_stddev < 20.0`. All four score `70-90`, roughly 3.5-4.5x the threshold.

### 3. Visual inspection (real thumbnails, actually viewed - not inferred from metadata)

Each thumbnail is one real decoded frame (~0.2s into the clip), extracted via `ffmpeg` on the GitHub Actions runner itself and base64-encoded into the job log (workaround for this session's own network policy blocking the GH artifact-storage host - see `.github/workflows/kaggle-free-inference.yml`'s "visual-inspection thumbnail" step).

**A (red sports car):** A car's rear end - visible spoiler, red taillights, parked/framed against a blue-neon-lit futuristic city street with horizontal light streaks. Clearly automotive, clearly nocturnal/neon, clearly "cinematic lighting." The car's own body color is hard to confirm under the blue lighting cast.

**B (house/mountains):** A house-like structure - triangular roof line, a round window/porthole, light-colored walls - in the foreground, with mountain-like silhouettes behind it, in a soft pink/blue sunrise palette. Composition and color story clearly differ from A.

**C (snowy mountain):** Jagged, peak-like silhouettes rendered in a painterly blue/purple/orange palette. The *shape* reads as mountains, but the result is considerably more abstract/painterly than the "realistic documentary style" the prompt asked for - the weakest style match of the four.

**D (robot):** A boxy, mechanical head/torso shape with glowing panel lines and rounded side pieces, against a blue-lit city backdrop consistent with A's city palette. Reads clearly as a robot/mechanical figure; only the head/upper body is in frame, so "walking" motion isn't visually confirmable from a single frame.

### 4. Prompt adherence scores (0-10, based on the actual thumbnail viewed)

| | Score | Why |
|---|---|---|
| A | 8/10 | Car anatomy (spoiler, taillights) and "night/cinematic lighting" both clearly present; can't confirm "red" body paint under the blue cast |
| B | 7/10 | House shape and mountain backdrop both present; palette reads more pink/blue than a strict "sunrise" gold |
| C | 5/10 | Mountain shape recognizable, but far more abstract/stylized than "realistic documentary style" calls for - weakest style adherence |
| D | 7/10 | Clearly mechanical/robotic and in a futuristic-city setting; "walking" can't be confirmed from a single static frame |

### 5. Temporal quality

`quality_metrics.py` samples 5 frames spread across each clip and reports per-frame stats; all four runs' sampled frames have real, non-zero, non-identical stddev (folded into the single `avg_stddev` figure above - none collapsed to the flat/near-zero-variance signature of the pre-fix era).

The denoising diagnostic (`latents_norm` at each of the 20 steps, logged per-run) shows the same smooth pattern in all four: starts at `~262`, decreases smoothly to a minimum of `~220-229` around step 13, then increases smoothly back up to `314-395` by the final step - a clean, monotonic-both-ways U-shape with no discontinuities, oscillation, or NaN in any of the four runs. This is evidence the denoising trajectory itself is numerically stable and not chaotic, which is a necessary (not sufficient) condition for coherent motion - it does not by itself confirm frame-to-frame visual smoothness, since that requires frame-differencing across the decoded video that this iteration did not compute (see Remaining weaknesses).

### 6. Applying the required success criteria

A video counts as successful only if **all** of: `avg_stddev` above the flat-frame threshold (20.0), frames differ from each other, requested elements are visible, and prompt conditioning is clearly non-generic (differs meaningfully across prompts). All four:

| Criterion | A | B | C | D |
|---|---|---|---|---|
| `avg_stddev` > 20 | ✅ 77.78 | ✅ 89.76 | ✅ 80.23 | ✅ 70.97 |
| Frames differ (not flat) | ✅ | ✅ | ✅ | ✅ |
| Requested elements visible | ✅ car | ✅ house+mountains | ⚠️ mountain shape, weak style match | ✅ robot |
| Prompt conditioning non-generic | ✅ (norms 17.16-18.94, sizes 35-56KB, 4 visually distinct thumbnails) | | | |

**Verdict: all four pass by the letter of the criteria; C passes on content but is the weakest on style fidelity.** This is a categorical change from every iteration 0001-0020, where the entire success question was moot - there was no text conditioning to evaluate at all.

### 7. Root-cause chain this closes

`transformers==5.0.0` (all-zero UMT5 output) → `transformers==4.48.0` (real UMT5 output, eval/reports/0021) → real, prompt-dependent `prompt_embeds_norm` inside the actual `WanPipeline` (this iteration) → real, prompt-dependent, non-flat video content (this iteration). Every link in this chain is now measured, not assumed.

### 8. Remaining weaknesses / known issues

- **Resolution and duration are both minimal** (`480x272`, 9 frames / ~0.56s @16fps) - the smallest configuration that avoids the VAE-decode OOM found in eval/reports/0008-0011. Real cinematic use needs both higher, untested here.
- **20 sampling steps is low** - this engine's own documented default is ~40; fine detail/texture at 20 steps has not been compared against higher step counts.
- **No frame-to-frame flicker/motion-smoothness metric exists yet** - `quality_metrics.py` samples 5 static frames independently; it does not compute optical flow or frame-differencing, so "motion stability" in section 5 is inferred indirectly from the denoising trajectory, not measured directly from the decoded video.
- **C's style adherence (5/10) is the one open quality question from this batch** - realistic/documentary style prompts may need a different guidance_scale or more steps than stylized ones; not yet isolated as a single-variable experiment.
- **T4's ~14.56 GiB usable VRAM remains the hard ceiling** on any resolution/frame-count increase - every future sweep dimension (steps, guidance, resolution, frames) has to be tested against real OOM risk, not just quality.

### 9. Current best/confirmed-working settings for Kaggle T4

`480x272`, `9` frames, `16fps`, `20` steps, `guidance_scale=6.0`, `seed=42`, `enable_sequential_cpu_offload=True`, `transformers==4.48.0`, `diffusers==0.37.1` - the only configuration confirmed, with real evidence, to produce non-flat, prompt-matching video on a free Kaggle T4 without OOM.

### 10. Next experiment

Per the user's own requested order: (1) confirm `transformers==4.48.0` has no reinstall path back to 5.x (done, see this branch's dependency audit), (2) sweep `num_inference_steps` (20/30/40), (3) sweep `guidance_scale` (5/6/7), (4) sweep `resolution` (480x272/640x360), (5) sweep `frame count` (9/17) - one variable at a time, each compared against this iteration's baseline. This is a real, multi-hour, ~10-run additional GPU commitment and is pending explicit user go-ahead before dispatch.
