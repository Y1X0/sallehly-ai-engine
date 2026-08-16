# Iteration 0016: CONFIRMED - text embeddings are genuinely zero, not a callback artifact

**Kaggle run:** [30373730220](https://github.com/Y1X0/sallehly-ai-engine/actions/runs/30373730220), commit `813c800`
**Prompt:** `A cinematic sunset over a futuristic city, high quality` (iteration 0013's own prompt)
**Params:** 480x272, 9 frames, 16fps, 20 steps, guidance_scale=6.0, seed=42 - identical to every prior iteration since 0011, no settings changed. Measure-only iteration per the user's explicit instruction: no fix attempted yet.

### 1. What was tested
The user's own framing, verbatim: does `pipeline.encode_prompt()` - WanPipeline's real internal text-encoding method, called directly, once, wrapped in `torch.no_grad()`, completely independent of `callback_on_step_end` and before the denoising loop or `enable_sequential_cpu_offload()`'s per-step hook cycle is ever engaged - report a real, nonzero embedding (proving eval/reports/0015's zero reading was a callback/offload-hook artifact), or does it also report exactly zero (proving the embeddings are genuinely zero and the text encoder itself is the root cause)?

(A first attempt at this exact test, run `30371065702`, crashed with a real CUDA OOM - traced to this diagnostic call itself: `WanPipeline.__call__` is `@torch.no_grad()`-decorated but the standalone `encode_prompt()` call wasn't, so it built a full autograd graph on top of the T4's already-tight memory budget. Fixed by wrapping the diagnostic call in `torch.no_grad()` and explicitly freeing its tensors before the real generation call - see commit `813c800`. This re-run is the corrected version.)

### 2. What failed / what was observed
**Every single statistic is exactly 0.0 - not just the norm:**
```json
"direct_prompt_embeds_shape": [1, 226, 4096],
"direct_prompt_embeds_dtype": "torch.bfloat16",
"direct_prompt_embeds_min": 0.0,
"direct_prompt_embeds_max": 0.0,
"direct_prompt_embeds_abs_mean": 0.0,
"direct_prompt_embeds_norm": 0.0,
"direct_negative_prompt_embeds_shape": [1, 226, 4096],
"direct_negative_prompt_embeds_dtype": "torch.bfloat16",
"direct_negative_prompt_embeds_min": 0.0,
"direct_negative_prompt_embeds_max": 0.0,
"direct_negative_prompt_embeds_abs_mean": 0.0,
"direct_negative_prompt_embeds_norm": 0.0
```
`min == max == 0.0` is the decisive detail: if even a single element of a 226x4096 tensor were nonzero, `min` and `max` could not both read exactly `0.0` at the same time (unless every element is precisely zero). This is not "very small" or "numerically negligible" - it is a tensor of all zeros, full stop.

The callback-based measurement (unchanged from eval/reports/0015) still also reads `prompt_embeds_norm: 0.0` at every one of the 20 denoising steps, in the same run. Both measurement paths - the callback and this new direct, no-callback call - now agree.

**One real, minor discrepancy worth flagging honestly:** this diagnostic's shape is `[1, 226, 4096]`, while the callback-observed shape (throughout eval/reports/0011-0015) is `[1, 512, 4096]`. `226` is `WanPipeline.encode_prompt()`'s own default `max_sequence_length` parameter, which this diagnostic call did not override; the real `pipeline()` call evidently passes a larger `max_sequence_length` (512) internally. This does not change the zero-value conclusion (both shapes are all-zero), but it means this diagnostic's exact tensor isn't byte-for-byte the same call the real generation makes - a fully equivalent follow-up would pass `max_sequence_length=512` explicitly. Noted for completeness, not treated as casting doubt on the core finding, since both the 226-length direct call and the 512-length callback observation independently land on all-zero.

### 3. Root cause
**Confirmed, not merely suspected: the text embeddings genuinely are zero-valued.** This rules out eval/reports/0015's "callback/`enable_sequential_cpu_offload()` instrumentation artifact" hypothesis outright - this measurement never touches the callback or the denoising loop at all.

Per the user's own explicit instruction for this iteration, **no fix is attempted here** - only the measurement and its documentation. Based on reading `WanPipeline._get_t5_prompt_embeds`'s real source (see eval/reports/0015's investigation groundwork), the mechanistically precise place this could happen is:
```python
prompt_embeds = self.text_encoder(text_input_ids.to(device), mask.to(device)).last_hidden_state
prompt_embeds = [u[:v] for u, v in zip(prompt_embeds, seq_lens)]  # v = seq_lens (real token count)
prompt_embeds = torch.stack([torch.cat([u, u.new_zeros(max_sequence_length - u.size(0), u.size(1))]) for u in prompt_embeds], dim=0)
```
where `seq_lens = mask.gt(0).sum(dim=1)`. If `seq_lens` comes back `0` for this prompt (i.e., the tokenizer's attention mask has no positions counted as "real" at all), `u[:v]` with `v=0` discards 100% of the text encoder's real output, and the subsequent zero-padding fills the *entire* sequence - which would produce exactly the all-zero tensor observed, regardless of what the text encoder itself actually computed internally. This is a candidate mechanism, not yet directly verified (verifying it would mean logging the tokenizer's raw `attention_mask`/`seq_lens` values directly - not done this iteration, per the user's "measure only" instruction).

### 4. Evidence
- `direct_prompt_embeds_min/max/abs_mean/norm` = `0.0`/`0.0`/`0.0`/`0.0`, from a call to `pipeline.encode_prompt()` made directly, wrapped in `torch.no_grad()`, before the denoising loop or its callback exist.
- Same result for `direct_negative_prompt_embeds_*`.
- Cross-checked against the callback-based `prompt_embeds_norm: 0.0` (all 20 steps) in the same run - both measurement paths agree.
- `gpu_name: "Tesla T4"`, `prompt: "A cinematic sunset over a futuristic city, high quality"` (correctly received, matching what was dispatched) - ruling out a job-input-passing issue as the explanation.
- Real diffusers 0.37.1 source, read directly: `WanPipeline.__call__` is `@torch.no_grad()`-decorated; `_get_t5_prompt_embeds`'s real zero-padding logic (quoted above) is a plausible, specific mechanism for an all-zero result when `seq_lens == 0`.

### 5. What was changed
Only this iteration's diagnostic code (already committed for eval/reports/0015, fixed in commit `813c800` for the OOM). No model, scheduler, seed, resolution, dtype, or tiling setting was changed - per the user's explicit instruction, this iteration measures and documents only.

### 6. Before vs after comparison
| Measurement path | prompt_embeds norm | Independent of callback? | Independent of `enable_sequential_cpu_offload`'s hook timing? |
|---|---|---|---|
| `callback_on_step_end` (eval/reports/0015) | 0.0 | No | No |
| Direct `pipeline.encode_prompt()` call, `torch.no_grad()` (this iteration) | **0.0** | **Yes** | **Yes** |

Both agree: the zero is real, not an instrumentation artifact.

### 7. Benchmark scores
Not applicable - this confirms the prerequisite blocker (real text conditioning is not reaching the model) that must be fixed before benchmarking is meaningful.

### 8. Remaining weaknesses
- The exact mechanism inside `_get_t5_prompt_embeds` (the `seq_lens == 0` hypothesis in section 3) has not been directly verified - it is a well-supported candidate based on reading the real source, not a confirmed root cause yet.
- This diagnostic used `max_sequence_length=226` (the method's default) rather than matching the real call's `512` - a fully apples-to-apples re-check would specify `max_sequence_length=512` explicitly, though this is not expected to change the all-zero result.
- No fix has been attempted yet, per the user's explicit instruction for this iteration.

### 9. Next experiment
Per the user's own stated plan: now that "does the prompt reach the model" is answered (no), the investigation should pivot to the tokenizer/prompt-embeddings/conditioning-passing path specifically, rather than continuing to adjust VAE/tiling. The most direct next diagnostic (still measurement, not yet a fix) would log the tokenizer's raw output for this exact prompt - `text_inputs.attention_mask` and the derived `seq_lens = mask.gt(0).sum(dim=1)` - immediately after tokenization inside `_get_t5_prompt_embeds`, to confirm or refute the `seq_lens == 0` mechanism directly rather than inferring it from source-reading alone.
