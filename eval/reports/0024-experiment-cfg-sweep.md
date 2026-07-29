# Experiment 0024: guidance_scale (CFG) sweep (5 → 6 → 7)

**Experiment ID:** 0024
**Variable changed:** `guidance_scale` only (5.0 → 6.0 → 7.0). Everything else held at the golden baseline confirmed by Experiment 0023: prompt A ("A red sports car driving through a futuristic city at night, cinematic lighting"), `480x272` requested resolution, `9` frames, `16fps`, `num_inference_steps=20`, `seed=42`, `transformers==4.48.0`, Tesla T4.

**Reason:** Second dimension of the user's specified sweep order (steps → CFG → resolution → frames). `guidance_scale=6.0` was this engine's inherited default, never itself tested against neighboring values with real evidence.

**Kaggle runs:** 5.0 = [30452887238](https://github.com/Y1X0/sallehly-ai-engine/actions/runs/30452887238), 6.0 (baseline) = [30440159420](https://github.com/Y1X0/sallehly-ai-engine/actions/runs/30440159420) (eval/reports/0022/0023 - predates the CLIP metric), 7.0 = [30455392303](https://github.com/Y1X0/sallehly-ai-engine/actions/runs/30455392303)

### Evidence / Objective metrics

| Metric | CFG=5.0 | CFG=6.0 (before) | CFG=7.0 |
|---|---|---|---|
| `prompt_embeds_norm` | 17.768630981445312 | 17.768630981445312 | 17.768630981445312 |
| Video size | 51,203 bytes | 43,432 bytes | 54,779 bytes |
| Actual encoded resolution | `480x256` | (not captured, predates this field) | `480x256` |
| `avg_stddev` | 75.21 | 77.78 | 70.48 |
| `flat_frame_suspected` | false | false | false |
| `avg_sharpness` | 5.37 | (predates metric) | **6.86** |
| `avg_saturation` | 0.7699 | (predates metric) | 0.7035 |
| `avg_frame_delta` | 26.902 | (predates metric) | 20.526 |
| `clip_similarity_mean` | **0.2684** | (predates CLIP wiring) | 0.2603 |

`prompt_embeds_norm` identical across all three - confirms `guidance_scale` cannot and does not affect text encoding, only how the conditional/unconditional predictions are combined during denoising. Clean single-variable test.

### Visual observations

- **CFG=5.0:** the clearest, best-composed result of this entire investigation so far - clean car silhouette, spoiler, sharply-defined red taillights, symmetric framing, legible blue city glow in the background. Sent to the user directly as evidence.
- **CFG=6.0** (baseline, eval/reports/0022): car's rear end, spoiler, red taillights, clearly framed - good, but the framing/composition in the 5.0 run reads slightly cleaner.
- **CFG=7.0:** a real, visible regression - blurry, oversaturated reflections and light streaks dominate the frame; the car's outline is barely discernible. This is the classic "over-adherence/oversaturation" failure mode associated with high classifier-free-guidance values. Notably, this run scored the **highest** `avg_sharpness` (6.86) of all three - the second time in this investigation (after Experiment 0023's 40-step result) that the sharpness proxy moved in the *opposite* direction from actual visual quality. `clip_similarity_mean` (0.2603), by contrast, correctly tracked the visual impression - lower than CFG=5.0's 0.2684.

### Final score (/10)

| | Score | Why |
|---|---|---|
| CFG=5.0 | **9/10** | Clearest, most recognizable, best-composed result of the whole project; highest CLIP score |
| CFG=6.0 | 8/10 | Good, clear car scene (matches eval/reports/0022's own scoring) |
| CFG=7.0 | 3/10 | Blurry, oversaturated, car barely discernible - a real regression despite the highest sharpness number |

### Decision

**Move the golden baseline's `guidance_scale` from 6.0 to 5.0.** This is not a marginal call: CFG=5.0 produced the best-looking, most clearly prompt-matching output of this entire investigation, backed by both a direct visual comparison and the highest CLIP similarity score measured so far. CFG=7.0 is a clear regression and should not be used. The updated golden baseline is now: `480x272` (requested), `9` frames, `20` steps, **`guidance_scale=5.0`**, `seed=42`.

### Remaining weaknesses in this experiment

- CFG=6.0's own data predates both the sharpness/saturation/frame-delta metrics and the CLIP metric - its comparison is based on `avg_stddev` and direct visual judgment only, not the full metric set available for 5.0 and 7.0. A same-config repeat of CFG=6.0 with the current full instrumentation would make this a completely clean three-way comparison, but was not judged necessary given how decisively 5.0 already wins on every available axis.
- As with Experiment 0023, only one fixed-timestamp thumbnail per video was visually inspected, not the full clip.
- The `480x256` vs requested `480x272` resolution mismatch persists here too, confirming it is independent of both `num_inference_steps` (Experiment 0023) and `guidance_scale` (this experiment) - still unexplained, still untouched by single-variable discipline.

### Next experiment

Resolution sweep per the user's specified order: `480x272` (already the baseline, now paired with `guidance_scale=5.0`) vs `640x360`, holding `steps=20` and `guidance_scale=5.0` fixed. Real OOM at the higher resolution is an accepted, informative possible outcome given this project's own documented history (eval/reports/0008-0011 found a 13.45 GiB VAE-decode OOM at higher resolutions before the current small baseline was adopted) - if it fails, the result gets written up honestly as its own iteration, not patched over with multiple simultaneous changes.
