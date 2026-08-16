# Iteration 0019: DECISIVE - weights are real and healthy with offload OFF, but the encoder output is STILL exactly zero. Per the user's own plan: stop pipeline experiments, investigate UMT5/checkpoint/transformers/diffusers itself.

**Kaggle run:** [30398479042](https://github.com/Y1X0/sallehly-ai-engine/actions/runs/30398479042), commit `a2f8239`
**Prompt:** `A cinematic sunset over a futuristic city, high quality`
**Params:** 480x272, 9 frames, 16fps, 20 steps, guidance_scale=6.0, seed=42, model, scheduler, tiling, dtype all unchanged from eval/reports/0017/0018 - **the only variable changed: `enable_sequential_cpu_offload()` was skipped** (`disable_sequential_cpu_offload=True`).

### 1. What was tested
The user's own decisive A/B: with everything else held identical to eval/reports/0017/0018's baseline, does disabling `enable_sequential_cpu_offload()` make the text encoder's weights real (non-meta) and its output nonzero - implicating offload as the cause - or does the output stay zero even with real weights, per the user's own explicit fallback ("توقف عن أي تجارب إضافية على الـ pipeline، وانتقل مباشرة للتحقيق في تحميل UMT5 نفسه")?

### 2. What failed / what was observed

**A real, unusually long run - itself informative:** the "wait for Kaggle kernel" step took **76.5 minutes** (20:56:27 to 22:13:08), roughly 5-6x every prior run's typical 13-15 minutes. Loading the full ~12B-parameter pipeline directly (transformer + text encoder + VAE, no staged/sequential device transfers) is dramatically slower without `enable_sequential_cpu_offload()`'s per-tensor management - a real, measured cost of this diagnostic-only toggle, consistent with why offload was adopted for this engine in the first place (eval/reports/0002 era).

**The weights are now confirmed real, healthy, and correctly loaded:**
```json
"text_encoder_any_meta_tensor": false,
"text_encoder_first_param_device": "cpu",
"text_encoder_first_param_is_meta": false,
"text_encoder_first_param_min": -187.0,
"text_encoder_first_param_max": 185.0,
"text_encoder_first_param_mean": -0.004248784389346838,
"text_encoder_first_param_std": 9.7021484375,
"text_encoder_first_param_norm": 262741.84375,
"text_encoder_first_param_nonzero_count": 1050148864
```
Compare directly to eval/reports/0018 (offload ON): `is_meta: true`, `device: "meta"` (no stats computed). With offload off, `shared.weight` is on a real device (`cpu`, at this measurement point - expected, since without offload the module hasn't yet been moved for its forward pass), has a normal, sane distribution (`min/max` -187/185, `std` ~9.7, not degenerate), and **1,050,148,864 of its elements are nonzero** - essentially the entire tensor (`256384 x 4096 = 1,050,673,664` total elements) is real, non-zero data. **The checkpoint loads correctly and the weights are genuinely healthy** when offload is disabled.

**But the raw encoder output is still exactly zero:**
```json
"trace_prompt_raw_encoder_output_min": 0.0,
"trace_prompt_raw_encoder_output_max": 0.0,
"trace_prompt_raw_encoder_output_abs_mean": 0.0,
"trace_prompt_raw_encoder_output_norm": 0.0
```
Identical to eval/reports/0017's offload-ON result. Real, healthy, non-meta, non-degenerate weights feed into the same `text_encoder(input_ids, attention_mask).last_hidden_state` call - and the result is still, exactly, entirely zero.

`video.mp4`: 21,056 bytes (a new, distinct size from every prior run - consistent with a real, if still content-less, generation completing).

### 3. Root cause
**Per the user's own explicit decision criteria, this is the disambiguating result: `enable_sequential_cpu_offload()` is NOT the cause.** Disabling it changed exactly one thing measurably - the weights are now visibly real/non-meta instead of appearing as a meta placeholder - and that change had **zero effect** on the actual symptom (the encoder's output is still exactly zero). This also, as a direct consequence, rules out "the checkpoint never loaded" as an explanation: the weights are unambiguously present, healthy, and non-degenerate (real min/max/std/norm, ~100% nonzero elements).

**What remains, following the user's own fallback exactly:** the failure is inside the UMT5 forward computation itself, or a `transformers`/`diffusers` version-compatibility issue in how that computation runs - not weight loading, not the offload mechanism, not the tokenizer, not the attention mask (all previously ruled out in eval/reports/0015-0018). Per the user's explicit instruction, no further pipeline-level experiments (tiling, resolution, dtype, offload) are warranted - the investigation must now target UMT5/checkpoint/library-version specifics directly.

### 4. Evidence
- Real Kaggle run `30398479042`, job log (`mcp__github__get_job_logs`), `output/metadata.json`'s echoed `text_encoder_*`/`trace_prompt_*` fields (quoted in full above).
- Direct before/after comparison against eval/reports/0017 (offload ON: `raw_encoder_output` all-zero) and eval/reports/0018 (offload ON: `text_encoder_first_param_is_meta: true`) - same config otherwise, single variable changed.
- `text_encoder_first_param_nonzero_count: 1,050,148,864` out of `256384 x 4096 = 1,050,673,664` total elements (99.95% nonzero) - decisively real weight data, not a placeholder or degenerate fill.
- The 76.5-minute run duration itself, a real, measured, order-of-magnitude slowdown versus every prior run's 13-15 minutes, confirming this was a genuine, complete, non-cached execution (not a fluke/short-circuit).

### 5. What was changed
Only the diagnostic toggle (`disable_sequential_cpu_offload=True`), already committed for this iteration (`a2f8239`). Model, prompt, seed, resolution, scheduler, tiling, dtype, and step count were all held identical to eval/reports/0017/0018, per the user's explicit instruction. No fix attempted.

### 6. Before vs after comparison
| Metric | 0017/0018 (offload ON) | 0019 (offload OFF, this iteration) |
|---|---|---|
| `text_encoder_first_param_is_meta` | `true` | **`false`** |
| `text_encoder_first_param_device` | `"meta"` | **`"cpu"`** |
| `text_encoder_first_param_norm` | n/a (meta, no data) | **`262741.84`** (real) |
| `text_encoder_first_param_nonzero_count` | n/a (meta, no data) | **`1,050,148,864`** (~100% of tensor) |
| `trace_prompt_raw_encoder_output_norm` | `0.0` | **`0.0` (unchanged)** |
| Run duration ("wait for kernel" step) | ~13-15 min | **~76.5 min** |
| `video.mp4` size | 20,645/21,736 bytes | 21,056 bytes (new, distinct) |

### 7. Benchmark scores
Not applicable - the prerequisite blocker (zero text conditioning) persists.

### 8. Remaining weaknesses
- The exact mechanism inside UMT5's forward computation (or a `transformers`/`diffusers` version mismatch) that turns real, healthy weights + real, healthy tokens/mask into an all-zero output is still unknown - this iteration rules out two of the three candidates from eval/reports/0018 (offload, weight-loading) but does not yet pinpoint the third.
- No fix has been attempted, per the user's explicit instruction throughout this whole line of investigation.

### 9. Next experiment
Per the user's own explicit fallback instruction for exactly this outcome: stop running further pipeline-level A/B experiments (tiling, resolution, dtype, offload have all now been examined) and investigate the UMT5 checkpoint/model loading and the `transformers`/`diffusers` library versions themselves. Concretely, candidates for the next diagnostic: (a) verify the exact `transformers` version installed on Kaggle (not yet logged - only `torch`/`diffusers` versions have been captured so far) and check it against any known UMT5-specific compatibility issues for that diffusers/transformers pairing; (b) run a minimal, standalone `UMT5EncoderModel.from_pretrained(...)` + manual forward pass outside the full `WanPipeline` (isolating whether the bug is in `WanPipeline`'s own use of the encoder or in the encoder/library itself); (c) compare against the official Wan2.2 example code's exact `transformers`/`diffusers` version pins, per the user's own earlier-listed diagnostic plan item.
