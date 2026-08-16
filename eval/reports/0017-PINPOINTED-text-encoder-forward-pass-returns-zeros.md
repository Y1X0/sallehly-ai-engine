# Iteration 0017: PINPOINTED - the T5 text encoder's own forward pass returns all-zero output, tokenizer and attention mask are both healthy

**Kaggle run:** [30376466443](https://github.com/Y1X0/sallehly-ai-engine/actions/runs/30376466443), commit `bb68f58`
**Prompt:** `A cinematic sunset over a futuristic city, high quality` (+ empty-string negative prompt, both traced)
**Params:** 480x272, 9 frames, 16fps, 20 steps, guidance_scale=6.0, seed=42 - unchanged since 0011. Measure-only iteration per the user's explicit instruction: no fix attempted.

### 1. What was tested
The user's own 4-way diagnostic, verbatim: given that eval/reports/0016 confirmed `prompt_embeds` is genuinely all-zero (not a callback artifact), *which specific stage* of `WanPipeline._get_t5_prompt_embeds` first produces or discards real values - (1) the tokenizer produces no real tokens, (2) the attention mask marks everything as padding, (3) the raw text encoder output is already zero before any slicing, or (4) a later slicing/zero-padding step erases real, nonzero encoder output?

### 2. What failed / what was observed
A manual, step-by-step reproduction of `_get_t5_prompt_embeds`'s exact real logic, tracing every stage the user asked for:

**Tokenization - healthy, real tokens produced:**
```
trace_prompt_input_ids_first20 = [320, 17443, 8378, 8239, 2371, 702, 289, 177946, 1931, 8517, 275, 3333, 6517, 1, 0, 0, 0, 0, 0, 0]
trace_prompt_non_pad_token_count = 14
trace_prompt_pad_token_id = 0
```
14 real, distinct, sensible-looking token IDs followed by an EOS token (`1`) and then padding (`0`) - this is completely normal T5 tokenization. **Hypothesis (1) is REJECTED**: the tokenizer works correctly.

**Attention mask - healthy, correctly marks the 14 real positions:**
```
trace_prompt_attention_mask_sum = 14        (matches non_pad_token_count exactly)
trace_prompt_attention_mask_unique = [0, 1]  (proper binary mask, not degenerate)
trace_prompt_seq_lens = [14]
trace_prompt_zero_pad_condition_triggered = false
```
**Hypothesis (2) is REJECTED**: the mask correctly identifies real vs. padding tokens, and the "discard everything because `seq_lens==0`" branch does *not* trigger (`seq_lens=14`, not `0`).

**The raw text encoder output itself - already all-zero, before any slicing or padding:**
```
trace_prompt_raw_encoder_output_shape = [1, 226, 4096]
trace_prompt_raw_encoder_output_min = 0.0
trace_prompt_raw_encoder_output_max = 0.0
trace_prompt_raw_encoder_output_abs_mean = 0.0
trace_prompt_raw_encoder_output_norm = 0.0
```
This is `self.text_encoder(input_ids, attention_mask).last_hidden_state`, captured **immediately** after the encoder's forward call, before any of `_get_t5_prompt_embeds`'s own slicing/zero-padding logic runs. It is already, entirely zero. **Hypothesis (3) is CONFIRMED.** (Consequently hypothesis (4) does not apply - there is no "later step" erasing real values, because there were no real values to erase in the first place.)

The negative prompt (empty string `""`) shows the identical pattern: 1 real token (`input_ids_first20 = [1, 0, 0, ...]`, an EOS-only encoding, which is the correct tokenization of an empty string), a healthy mask (`sum=1`, `seq_lens=1`, `zero_pad_condition_triggered=false`), and again `raw_encoder_output_min/max/abs_mean/norm` all exactly `0.0`. The zero-output failure is not specific to this one prompt string - it reproduces identically for two very different inputs (a 14-token real sentence and a 1-token empty string), pointing at something systemic in the encoder's forward pass itself rather than anything input-dependent.

### 3. Root cause
**Pinpointed to a single stage, with the other three explicitly ruled out by direct measurement (not inference):** `pipeline.text_encoder`'s own forward pass (`UMT5EncoderModel.__call__`) returns an all-zero `last_hidden_state` for every input tried so far, despite receiving well-formed, correctly-tokenized `input_ids` and a correctly-computed `attention_mask`. Tokenization is healthy. The attention mask is healthy. The zero-padding/slicing logic in `_get_t5_prompt_embeds` never even gets the chance to matter, because its input (the raw encoder output) is already zero.

This directly, and finally, explains the flat/muddy/content-less output that has persisted since iteration 0001: with `prompt_embeds` completely zero regardless of input text, the transformer has no text conditioning signal whatsoever, generating an unconditional "average" scene every time - matching every visual observation from every prior iteration (flat, low-variance, no recognizable subject, no sensitivity to prompt or `guidance_scale`).

**Not yet determined (would require code changes, out of scope for this measure-only iteration):** *why* the text encoder itself returns zeros. Plausible candidates, none tested yet:
- The `enable_sequential_cpu_offload()` hook managing `text_encoder`'s weights may not be correctly materializing them on-device before this forward call fires (e.g. a race, or the module being called while its parameters are still on a `meta`/placeholder device).
- The text encoder's weights may not have loaded correctly from the HF Hub checkpoint (corrupted/partial download, or the wrong submodule) - though this would be surprising given `WanPipeline.from_pretrained()` completes without error and produces a real, distinctly-sized `video.mp4` for different seeds/resolutions across the whole investigation.
- Something specific to calling `text_encoder` directly (as this diagnostic does, mirroring `_get_t5_prompt_embeds`'s own exact call) versus how it is invoked inside the full `pipeline()` call - though this diagnostic replicates the identical call signature (`self.text_encoder(text_input_ids.to(device), mask.to(device))`) used internally, so this seems unlikely to be a distinguishing factor.

### 4. Evidence
- Real Kaggle run `30376466443`, job log (`mcp__github__get_job_logs`), `output/metadata.json`'s echoed `trace_prompt_*`/`trace_negative_prompt_*` fields (quoted in full above).
- Two independent inputs (14-token real prompt, 1-token empty-string negative prompt) both show healthy tokenization + healthy attention mask + all-zero raw encoder output - ruling out an input-specific quirk.
- Direct reproduction of `WanPipeline._get_t5_prompt_embeds`'s own real logic (read from diffusers 0.37.1 source in eval/reports/0015/0016), called with the identical arguments the real pipeline uses internally.

### 5. What was changed
Nothing beyond the diagnostic trace itself (already committed for this iteration, `bb68f58`). No model, scheduler, seed, resolution, dtype, or tiling setting was touched. No fix attempted, per the user's explicit instruction.

### 6. Before vs after comparison
| Stage | Status |
|---|---|
| Tokenizer (`input_ids`, `non_pad_token_count`) | **Healthy** - 14 real tokens for the real prompt, 1 (EOS) for empty string |
| Attention mask (`sum`, `unique`, `seq_lens`) | **Healthy** - correctly marks real vs. padding, `seq_lens` matches token count exactly |
| Zero-pad-everything branch (`seq_lens==0`) | **Not triggered** - confirmed `false` for both prompts |
| Raw text encoder output (`last_hidden_state`) | **All zero** - `min=max=abs_mean=norm=0.0`, before any further processing |
| Final embeds (after slice + pad, matching `_get_t5_prompt_embeds`'s own logic) | **All zero** - inherited entirely from the already-zero raw output |

### 7. Benchmark scores
Not applicable - this is the confirmed, pinpointed prerequisite blocker.

### 8. Remaining weaknesses
- *Why* `text_encoder`'s forward pass returns zeros is still open (see the three candidates in section 3) - this iteration pinpoints *where*, not yet *why*.
- No fix has been attempted, per the user's explicit instruction for this iteration.

### 9. Next experiment
Now that the failure is pinpointed to the text encoder's own forward pass (not tokenization, not the attention mask, not a later slicing step), the highest-value next diagnostic - still measurement, one variable at a time - would check whether `enable_sequential_cpu_offload()` is implicated: run the identical trace with sequential CPU offload disabled (accepting the OOM risk this has previously caused at this resolution, or testing at a resolution/frame-count already confirmed to fit without it) to see whether `raw_encoder_output` becomes real once the offload hooks are out of the picture. A second, cheaper diagnostic worth trying first: print `pipeline.text_encoder.dtype` and a representative weight tensor's own `.norm()` (e.g. the first transformer block's first linear layer) immediately before the forward call, to check whether the encoder's *weights themselves* are already zero (a loading/offload problem) versus the weights being real but the *forward computation* zeroing everything (an architecture/call-argument problem).
