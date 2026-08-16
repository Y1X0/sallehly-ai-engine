# Experiment 0025: resolution sweep (480x272 vs 640x352) - and a real code-level root cause found

**Experiment ID:** 0025
**Variable changed:** resolution only. Everything else held at the golden baseline confirmed by Experiments 0023/0024: prompt A ("A red sports car driving through a futuristic city at night, cinematic lighting"), `9` frames, `16fps`, `num_inference_steps=20`, `guidance_scale=5.0`, `seed=42`, `transformers==4.48.0`, Tesla T4.

**Reason:** Third dimension of the user's specified sweep order (steps → CFG → resolution → frames).

## Part 1: 640x360 - a real failure, but not the one anticipated

**Problem:** `640x360` failed. The user's own prior instruction anticipated a possible CUDA OOM (given eval/reports/0008-0011's documented 13.45 GiB VAE-decode OOM history at higher resolutions) and asked for that outcome to be documented honestly as a hard ceiling, without trying to work around it.

**Evidence:** The real Kaggle run ([30469864044](https://github.com/Y1X0/sallehly-ai-engine/actions/runs/30469864044)) failed with:
```
FAILED - the kernel ran and reported a real error: ValueError: `height` and `width` have to be divisible by 16 but are 360 and 640.
```
This is `WanPipeline.check_inputs()`'s own hard validation (confirmed by reading `diffusers==0.39.0`'s real installed source directly): `if height % 16 != 0 or width % 16 != 0: raise ValueError(...)`. `360 / 16 = 22.5` - not an integer.

**Root cause:** Not a memory limit at all - a plain, deterministic input-validation failure. `640x360` was simply an invalid resolution for this pipeline, unrelated to Kaggle's T4 or this project's code. **Single-variable discipline note:** since 360 was never a valid input to begin with, no real information about resolution *capacity* was gained from this run - it had to be corrected and re-tested before the actual question (does higher resolution help?) could be answered.

## Part 2: the deeper investigation - what "divisible by 16" is hiding

The user asked a sharper question: eval/reports/0023/0024 both found the *actual* encoded resolution came back `480x256`, not the requested `480x272`, even though 272 **is** itself divisible by 16 (272/16=17). That contradiction meant the real constraint had to be something stricter than the error message's own "divisible by 16" - and it turned out to be exactly that.

Reading `WanPipeline.__call__`'s real source directly (not guessed) shows a **second**, silent adjustment after `check_inputs()`'s hard 16-check:
```python
patch_size = self.transformer.config.patch_size
h_multiple_of = self.vae_scale_factor_spatial * patch_size[1]
w_multiple_of = self.vae_scale_factor_spatial * patch_size[2]
calc_height = height // h_multiple_of * h_multiple_of
calc_width = width // w_multiple_of * w_multiple_of
if height != calc_height or width != calc_width:
    logger.warning(f"`height` and `width` must be multiples of ({h_multiple_of}, {w_multiple_of}) for proper patchification. Adjusting ({height}, {width}) -> ({calc_height}, {calc_width}).")
    height, width = calc_height, calc_width
```
Reading the real checkpoint's own config files directly from HF Hub confirmed the exact numbers for `Wan-AI/Wan2.2-TI2V-5B-Diffusers`:
- `transformer/config.json`: `"patch_size": [1, 2, 2]` → `patch_size[1] = 2`
- `vae/config.json`: `"scale_factor_spatial": 16`

So the *real* constraint for this specific checkpoint is `16 x 2 = 32`, not the 16 that `check_inputs()`'s error message names. This fully explains the mystery with real arithmetic, no guessing:
- `272 // 32 * 32 = 256` - exactly matches the `480x256` seen in eval/reports/0023/0024.
- `480 // 32 * 32 = 480` - already a multiple of 32, unaffected (matches width staying `480` in every prior run).
- `352 // 32 * 32 = 352` - already exact, predicting **no** further silent rounding at `640x352`.

This is not a bug in this project's code - it's an internal, silent (only `logger.warning()`-level, easy to miss) behavior of `WanPipeline` itself for this checkpoint. **Documented finding: real resolutions for this Wan2.2-TI2V-5B checkpoint must be multiples of 32, not just 16, to get the resolution you actually asked for.**

## Part 3: 640x352 (a valid, corrected retry) - a real, decisive resolution finding

**Kaggle run:** [30478446581](https://github.com/Y1X0/sallehly-ai-engine/actions/runs/30478446581)

**Evidence confirms the theory directly:** `"requested_resolution": "640x352"`, `"actual_resolution": "640x352"` - identical, no silent rounding, exactly as predicted.

### Objective metrics

| Metric | 480x272 (before, =0024) | 640x352 (after) |
|---|---|---|
| Video size | 51,203 bytes | 61,737 bytes |
| Generation time | ~14 min | ~15 min |
| `prompt_embeds_norm` | 17.768630981445312 | 17.768630981445312 |
| `avg_stddev` | 75.21 | 33.09 |
| `flat_frame_suspected` | false | false |
| `avg_sharpness` | 5.37 | 3.588 |
| `avg_saturation` | 0.7699 | 0.4172 |
| `avg_frame_delta` | 26.902 | 9.468 |
| `clip_similarity_mean` | 0.2684 | **0.2977** (highest of the whole investigation) |

`prompt_embeds_norm` identical - confirms a clean single-variable test (resolution can't affect text encoding).

### Visual observations

This is the most decisive visual result of the entire investigation. At `640x352`, for the first time, the video clearly shows: a genuinely **red** car body (every prior thumbnail's car color was obscured by blue lighting), the car's **full side profile** (not just a rear crop), correctly-proportioned wheels and body panels, a legible headlight/taillight, and motion-appropriate light-streak road markings. It reads as a real, coherent automotive shot - a categorical improvement over every 480x272 result, despite every raw pixel-stat metric (`avg_stddev`, `avg_sharpness`, `avg_saturation`, `avg_frame_delta`) reading *lower* than the 480x272 baseline.

This is the clearest demonstration yet in this project of pixel-stat proxies actively pointing the wrong way (following eval/reports/0023 and 0024's smaller-scale versions of the same pattern): a genuinely higher-quality, more prompt-matching video scored lower on every simple pixel-variance metric. `clip_similarity_mean` (0.2977, the highest of the whole investigation) is the one metric that correctly tracked the real visual improvement.

### Final score (/10)

| | Score | Why |
|---|---|---|
| 480x272 | 9/10 | Best result at its own resolution (eval/reports/0024) |
| 640x352 | **10/10** | First run to clearly show the car's actual red color and full profile; highest CLIP score measured; comparable generation time (~15 min vs ~14 min) |

### Decision

**Move the golden baseline resolution from 480x272 to 640x352.** The generation-time cost is negligible (~1 extra minute), and the visual/CLIP evidence is decisive, not marginal - this is the single clearest quality jump found in the entire hyperparameter sweep (Experiments 0023-0025). Pixel-stat metrics (`avg_stddev`/`avg_sharpness`/`avg_saturation`/`avg_frame_delta`) should be treated as secondary signals from this point on; CLIP similarity and direct visual inspection are the trustworthy ones.

**New golden baseline / Baseline v1.0: `640x352`, `9` frames, `20` steps, `guidance_scale=5.0`, `seed=42`, `transformers==4.48.0`.**

### Remaining weaknesses in this experiment

- Only one resolution above the original baseline was tested (`640x352`); whether further increases (e.g. `768x416`, still a multiple of 32) continue improving quality, plateau, or eventually hit a real memory ceiling is unknown and untested here - per the user's own redirection, this is deliberately not pursued further right now in favor of the robustness benchmark.
- The `h_multiple_of`/`w_multiple_of` = 32 finding is specific to this checkpoint's own `patch_size`/`scale_factor_spatial` config values - a different Wan2.1/2.2 variant could have different values and a different true multiple. This is now a documented, code-verified fact for `Wan-AI/Wan2.2-TI2V-5B-Diffusers` specifically, not a general claim about all Wan models.

### Next experiment

Per the user's explicit redirection: **stop the hyperparameter sweep here.** Do not test frame count (9 vs 17) or push resolution further right now. Freeze **Baseline v1.0** (`640x352`, `9` frames, `20` steps, `guidance_scale=5.0`, `seed=42`) and move to a robustness benchmark: run this exact frozen configuration across a broad set of prompts from `eval/benchmark_prompts.yaml`'s 30-category suite, to find which content categories (faces, animals, night scenes, fast motion, etc.) the model handles well or poorly - that result, not further hyperparameter tuning, should set the next real development priority.
