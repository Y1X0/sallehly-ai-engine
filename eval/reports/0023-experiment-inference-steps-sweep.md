# Experiment 0023: inference_steps sweep (20 → 30 → 40)

**Experiment ID:** 0023
**Variable changed:** `num_inference_steps` only (20 → 30 → 40). Everything else held fixed at the golden baseline: prompt A ("A red sports car driving through a futuristic city at night, cinematic lighting"), `480x272` requested resolution, `9` frames, `16fps`, `guidance_scale=6.0`, `seed=42`, `transformers==4.48.0`, `enable_sequential_cpu_offload=True`, Tesla T4.

**Reason:** First dimension of the user's specified sweep order (steps → CFG → resolution → frames), one variable at a time. This engine's own documented default is ~40 steps; eval/reports/0022's baseline used 20 (chosen to keep the first trial runs short) - unconfirmed whether the lower step count costs any real quality.

**Kaggle runs:** 20 steps = [30440159420](https://github.com/Y1X0/sallehly-ai-engine/actions/runs/30440159420) (eval/reports/0022), 30 steps = [30448674355](https://github.com/Y1X0/sallehly-ai-engine/actions/runs/30448674355), 40 steps = [30450561579](https://github.com/Y1X0/sallehly-ai-engine/actions/runs/30450561579)

### Evidence / Objective metrics

| Metric | 20 steps (before) | 30 steps | 40 steps (after) |
|---|---|---|---|
| `prompt_embeds_norm` | 17.768630981445312 | 17.768630981445312 | 17.768630981445312 |
| Video size | 43,432 bytes | 40,889 bytes | 38,559 bytes |
| Actual encoded resolution | (not captured in 0022) | `480x256` | `480x256` |
| `avg_stddev` | 77.78 | 69.21 | 63.66 |
| `flat_frame_suspected` | false | false | false |
| `avg_sharpness` | (metric added after this run) | 3.659 | 6.174 |
| `avg_saturation` | (metric added after this run) | 0.693 | 0.7268 |
| `avg_frame_delta` | (metric added after this run) | 29.023 | 29.47 |
| `clip_similarity_mean` | (CLIP wiring added after this run) | (predates CLIP wiring) | **0.259** |
| Generation time (Kaggle wait step) | ~14 min | ~15.5 min | ~15.5 min |

`prompt_embeds_norm` being bit-for-bit identical across all three confirms this is a clean single-variable test - `num_inference_steps` cannot and does not affect text encoding, only the denoising loop.

**Real, unplanned finding:** the actual encoded video resolution came back `480x256`, not the requested `480x272`, for both the 30-step and 40-step runs (0022 didn't capture width/height so it's unconfirmed there, but the same rounding almost certainly applied). This is step-count-independent (identical in both runs) - most likely a VAE/transformer internal patch-size constraint silently rounding `272` down to the nearest multiple its architecture requires, not a bug introduced by this experiment. Not yet root-caused; flagged as a real open item, not guessed at further here.

**CLIP wiring's first real-world result:** the 40-step run is also the first real Kaggle GPU run to include the newly-added CLIP prompt-adherence metric (eval/reports/0022's follow-up engineering work, merged mid-sweep). It worked correctly on the first real attempt: `clip_model: "openai/clip-vit-base-patch32"`, 9 real per-frame cosine similarities (`0.216-0.275`), `clip_similarity_mean: 0.259`. No baseline CLIP score exists for 20/30 steps (both predate this commit reaching the branch before their Kaggle kernels cloned it) - a same-config repeat at 20 steps is needed for a clean CLIP-based before/after in a future experiment.

### Visual observations

- **20 steps** (eval/reports/0022): car's rear end, spoiler, red taillights, clearly framed against a blue-neon city street.
- **30 steps:** same car/city scene, wider framing (more car body and buildings visible), comparable clarity to 20 steps - no obvious sharpness or detail improvement despite 50% more denoising steps.
- **40 steps:** a real, honest **regression in recognizability** - the sampled frame (fixed at ~0.2s into the clip, same nominal timing as the other two) no longer clearly reads as "car rear in a city street." It shows horizontal light streaks and indistinct shapes; the car's outline is barely inferable. This happened despite `avg_sharpness` being *highest* at 40 steps (6.174 vs 3.659 at 30) - a concrete example of a pixel-stat proxy (sharpness) not tracking actual prompt-adherence/recognizability. `clip_similarity_mean=0.259` is a moderate-low score (CLIP cosine similarities for a clearly-matching image/caption pair are typically higher, often 0.3+), consistent with this visual impression rather than contradicting it.

### Final score (/10)

| | Score | Why |
|---|---|---|
| 20 steps | 8/10 | Clear, recognizable, prompt-matching (matches eval/reports/0022's own scoring) |
| 30 steps | 7/10 | Comparably clear, no measurable improvement over 20, costs ~10% more GPU time |
| 40 steps | 4/10 | Higher sharpness metric but visually the weakest of the three at this exact sampled timestamp - a real regression in recognizable content, not an improvement |

### Decision

**Keep `num_inference_steps=20` as the golden baseline.** Neither 30 nor 40 steps demonstrated a real quality improvement on this prompt/resolution/frame-count; 40 steps showed a visible regression in the one sampled frame, and none of the three differ enough to justify the extra ~10-15% GPU time per generation, given Kaggle's free but finite weekly quota. This is a "more steps ≠ better" result specific to this engine/resolution/frame-count - not a general claim about diffusion step counts.

### Remaining weaknesses in this experiment

- Only one sampled frame per video was visually inspected (the thumbnail is always taken at a fixed 0.2s timestamp) - a single frame is not a full judgment of overall video quality across all 9 frames. `quality_metrics.py`'s 5-sample `per_frame_stats` exist for this reason but weren't individually visually rendered here, only aggregated into `avg_stddev`/`avg_sharpness`.
- No CLIP baseline exists for 20/30 steps to compare against 40 steps' `0.259` - the CLIP metric landed mid-sweep. A same-config 20-step repeat with CLIP active is worth doing before fully closing this question.
- The `480x256` vs requested `480x272` resolution mismatch is unexplained and untouched by this experiment - flagged for a future investigation, not fixed here (single-variable discipline: this experiment only varies steps).

### Next experiment

Move to the CFG/`guidance_scale` sweep (5/6/7) per the user's specified order, holding `num_inference_steps=20` (this experiment's confirmed decision) and everything else at the golden baseline. The `guidance_scale` workflow input has been added to `kaggle-free-inference.yml` for this purpose (it existed as a `dispatch_inference.py` CLI flag but was never exposed as a workflow input before this sweep needed it).
