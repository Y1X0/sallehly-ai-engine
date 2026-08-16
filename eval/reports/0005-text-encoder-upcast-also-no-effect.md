# Iteration 0005: text_encoder fp32 upcast (T5-family fp16 overflow hypothesis)

**Kaggle run:** [30333553288](https://github.com/Y1X0/sallehly-ai-engine/actions/runs/30333553288), commit `79fb0e1`
**Prompt:** `A cinematic sunset over a futuristic city, high quality` (unchanged since 0001)
**Params:** 960x544, 17 frames, 16fps, 20 steps, guidance_scale=6.0, seed=0 - single-variable change: `pipeline.text_encoder` upcast to fp32

### 1. What was tested
Whether the flat/degenerate output (iterations 0001-0004) is caused by
`UMT5EncoderModel` (the T5-family text encoder) overflowing in fp16 -
the same failure mode already found and fixed once for the VAE, never
previously applied to the text encoder.

### 2. What failed / what was observed
`metadata.json` confirms the same correct wiring as iteration 0004:
```json
{
  "prompt": "A cinematic sunset over a futuristic city, high quality",
  "negative_prompt": null,
  "guidance_scale": 6.0
}
```
`video.mp4` is **still exactly 127,355 bytes - the 5th consecutive
identical result** (0001-0005 all produced this exact byte count).
Kernel duration was 1260s - in the same ~1200-1310s range as
iterations 0003/0004 (both `guidance_scale=6.0`), not meaningfully
different, which is itself informative: `text_encoder` is a small
fraction of the pipeline's total compute compared to the 5B-parameter
transformer, so an unchanged duration here is expected regardless of
whether the fix worked - duration was never a useful signal for this
particular change (unlike it was for guidance_scale, where CFG adds a
whole second transformer forward pass).

### 3. Root cause
**The text-encoder-fp16-overflow hypothesis from iteration 0004 is now
also ruled out** - upcasting it produced zero measurable change,
exactly like the VAE upcast in iteration 0002.

This means both non-transformer fp16 submodules in the pipeline (VAE,
text encoder) have now been individually upcast to fp32 and neither
changed the output at all. **The only remaining fp16 component in the
entire pipeline is `WanTransformer3DModel` itself** - the actual
denoising transformer, and by far the largest (5B parameters) and most
computationally central part of the model. By systematic elimination,
if the degeneracy isn't in the VAE decode and isn't in the text
encoding, the most evidence-consistent remaining explanation is that
it originates inside the transformer's own fp16 forward pass -
consistent with everything observed so far:
- Explains why CFG is a no-op regardless of guidance_scale (if the
  transformer's fp16 computation saturates/overflows in a way that
  swamps out whatever `encoder_hidden_states` it's given, both the
  conditional and unconditional forward passes would converge to
  similar degenerate output regardless of which text produced them).
- Explains why fixing VAE and text-encoder precision individually had
  no effect (by the time either correctly-computed value reaches or
  leaves the transformer, the transformer's own internal degeneracy
  has already determined the output).

**Not yet confirmed** - this is the next hypothesis to test, not a
proven conclusion, per this project's own evidence discipline.

### 4. Evidence
- `metadata.json` (quoted above) - confirms guidance_scale/prompt wiring unchanged from iteration 0004, ruling out a regression in the diagnostic logging itself.
- `video.mp4` byte count: 127,355 - identical to iterations 0001-0004 (5 consecutive occurrences of the exact same number).
- Kernel duration: 1260s, consistent with iterations 0003 (1199s)/0004 (1311s) which share the same `guidance_scale=6.0` - not meaningfully different, confirming text_encoder upcast has negligible compute cost as expected (a real, if minor, corroborating data point that the change was applied but is small relative to the transformer).
- Process of elimination: VAE (0002) and text_encoder (0005) individually confirmed to have zero effect on output when upcast to fp32 - `WanTransformer3DModel` is the only remaining fp16 submodule.

### 5. What was changed
`pipeline.text_encoder = pipeline.text_encoder.to(torch.float32)` in
`wan_inference.build_real_pipeline()`. Confirmed to have had no
measurable effect.

### 6. Before vs after comparison
| Metric | 0004 (text_encoder fp16) | 0005 (text_encoder fp32) |
|---|---|---|
| video.mp4 size | 127,355 | 127,355 (identical) |
| Kernel duration | 1311s | 1260s (within noise, both guidance_scale=6.0) |
| guidance_scale/prompt wiring | confirmed correct | confirmed correct |

### 7. Benchmark scores
Unchanged from iterations 0001/0003/0004 (0/10 overall) - no evidence
yet of any output change across 5 iterations.

### 8. Remaining weaknesses
- Root cause still not confirmed. Two of three fp16 submodules (VAE,
  text encoder) are now ruled out by direct, isolated testing.
- Upcasting the transformer itself carries real risk: at 5B parameters,
  fp32 roughly doubles its weight footprint (~10GB fp16 -> ~20GB fp32)
  and increases per-step activation memory, on a GPU (T4) that already
  needed `enable_sequential_cpu_offload()` + VAE tiling/slicing to fit
  at all. This may reintroduce an OOM - which would itself be
  diagnostic (if it OOMs specifically during the transformer's own
  forward pass, that's further evidence this component is where the
  real numerical/memory pressure concentrates) rather than a wasted
  iteration either way.

### 9. Next experiment
Upcast `pipeline.transformer` (and `pipeline.transformer_2` if the
loaded config has one - Wan2.2-TI2V-5B is understood to be a single
dense transformer with no MoE split, but check
`pipeline.transformer_2 is not None` defensively rather than assume)
to `torch.float32`, completing the systematic elimination of every
fp16 submodule in the pipeline. If this also produces no change, the
next report must stop hypothesizing about precision entirely and
instead add direct tensor-level diagnostics (e.g. logging the L2 norm
of `noise_pred` vs `noise_uncond` at the first denoising step) to see
whether the two branches are numerically converging, or investigate
the latent initialization/generator/scheduler path instead.
