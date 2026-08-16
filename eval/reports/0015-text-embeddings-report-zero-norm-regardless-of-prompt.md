# Iteration 0015: prompt_embeds_norm is exactly 0.0 regardless of prompt - the user's "does the model see the prompt?" hypothesis

**4 real Kaggle runs, same commit (`c418e42`), same config throughout (480x272, 9 frames, 20 steps, seed=42, guidance_scale=6.0 default):**
- [30360209748](https://github.com/Y1X0/sallehly-ai-engine/actions/runs/30360209748) - prompt dispatched as `""`, silently became the workflow's own default `"A calm lake at sunrise, gentle ripples, warm golden light, cinematic"` (see caveat #1 below)
- [30360289845](https://github.com/Y1X0/sallehly-ai-engine/actions/runs/30360289845) - `"A red car"`
- [30361353120](https://github.com/Y1X0/sallehly-ai-engine/actions/runs/30361353120) - `"A snowy mountain at sunrise"`
- [30364299854](https://github.com/Y1X0/sallehly-ai-engine/actions/runs/30364299854) - dispatched as `" "` (single space, a workaround attempt for empty), **also** silently became the same lake default (see caveat #1)
- [30364516406](https://github.com/Y1X0/sallehly-ai-engine/actions/runs/30364516406) - **control run**: iteration 0013's own original prompt, `"A cinematic sunset over a futuristic city, high quality"`, re-run on the current commit

### 1. What was tested
The user's own next-priority hypothesis, ranked above further VAE/tiling work once memory, NaN, tile-seam, and seed causes were each ruled out: **does the transformer actually receive different text conditioning for different prompts, or is the conditioning signal lost/degenerate regardless of input text?** Per the user's exact instructions: three real generations (empty / "A red car" / "A snowy mountain at sunrise") at an otherwise-identical config, comparing results; plus GPU/torch/diffusers/dtype logging added first (eval/reports/0014 follow-through, commit `c418e42`).

### 2. What failed / what was observed

**Caveat #1 - a second, distinct GitHub Actions quirk found by hand:** `workflow_dispatch`'s API silently substitutes a `required: true` input's declared default whenever the dispatched value is empty (confirmed: `prompt=""`) **or whitespace-only** (confirmed: `prompt=" "` - a single space also got replaced by the same default). Neither of the two "empty prompt" dispatch attempts actually reached the pipeline as empty - both silently ran with the workflow's own default prompt instead. This is now a known, load-bearing quirk of this dispatch mechanism, not a guess - documented here so the next real empty-prompt attempt doesn't repeat it (a true empty-prompt test needs a code-level workaround - e.g. a sentinel string translated to `""` inside `dispatch_inference.py`/`wan_inference.py` - not a bare empty string dispatched through the Actions API).

**The actual, decisive finding - identical across all 4 runs, 3 of them genuinely different real prompts:**
```
prompt_embeds_norm:          0.0   (all 20 steps, all 4 runs)
negative_prompt_embeds_norm: 0.0   (all 20 steps, all 4 runs)
latents_norm trajectory:     261.85 -> 195.79 (same 20 values, all 4 runs)
video.mp4 size:               20645 bytes (all 4 runs, identical)
```
`prompt_embeds`/`negative_prompt_embeds` are real, non-NaN, non-Inf, correctly-shaped (`[1, 512, 4096]`, `bfloat16`) tensors in every run - but their L2 norm is **exactly** `0.0`, not just small. A 512x4096-element tensor computing to a norm of precisely `0.0` (not a tiny nonzero float) means the tensor is (numerically) all zeros - this is not a rounding/precision artifact.

**The control run is what makes this decisive rather than merely suspicious:** run `30364516406` used iteration 0013's *exact* prompt string, on this session's exact current code (`c418e42`) - the same prompt that produced a real, non-zero `prompt_embeds_norm: 41.77052688598633` / `negative_prompt_embeds_norm: 5.926913738250732` in iteration 0013 (re-verified directly from that iteration's locally-saved `metadata.json`, not just the log). On this run, the identical prompt now reports `0.0`. **This proves the zero-embeddings result is not caused by which prompt was used** - the same prompt gives a real embedding in one run and a zero embedding in another, with the tokenizer/model code path unchanged. Something session/state-dependent, not prompt-dependent, is producing the zero.

This is also fully self-consistent with everything else observed: if `prompt_embeds`/`negative_prompt_embeds` are both genuinely zero, the classifier-free-guidance formula (`noise_uncond + guidance_scale*(noise_pred - noise_uncond)`) has nothing to differentiate between its conditional and unconditional branches - both see the same (zero) conditioning - which explains, in one stroke, why the latent trajectory and the final video are byte-identical (or near enough - same size) across three unrelated prompts, and retroactively explains eval/reports/0003's original finding that `guidance_scale` 1.0->6.0 had "zero measurable effect" all the way back in the very first iterations of this investigation.

### 3. Root cause
**Not yet fully isolated - two candidate explanations remain open, and the honest, non-guessed position is that either is currently plausible:**

1. **A real bug in the text-conditioning path** (tokenizer, `_get_t5_prompt_embeds`, or the T5 encoder's forward pass itself) that occasionally - not always, since iteration 0013 had real embeddings - produces an all-zero output, independent of the input text. If real, this single bug would explain the flat/muddy/content-less output that has persisted since iteration 0001: a transformer conditioned on all-zero text embeddings degenerates to an unconditional, "average scene" generation, which is exactly the flat, structureless, low-variance output seen in every iteration to date.
2. **An artifact of this investigation's own diagnostic instrumentation**: `callback_on_step_end`'s `prompt_embeds`/`negative_prompt_embeds` tensors could in principle be exposed to a race with `enable_sequential_cpu_offload()`'s device-transfer hooks (which move individual weight tensors, and potentially intermediate activations, between GPU/CPU around each forward call) - if an offload hook clears/reuses the underlying storage right after the callback captures a reference but before `.norm()` reads it, the callback would report a zero norm on a tensor the transformer itself may have already consumed correctly. This would mean the transformer might still be seeing real conditioning internally - just not what this callback observes.

Both explanations are equally consistent with everything observed so far (the norm is exactly 0.0, not NaN/Inf, ruling out a numerical-overflow explanation like earlier fp16 hypotheses). They are not consistent with each other's implied next step, so isolating which one is real is the single highest-priority next action - not a further prompt A/B (that question is now answered: it doesn't matter which prompt is used, the embeddings read as zero either way).

### 4. Evidence
- 4 real Kaggle runs, `output/metadata.json` (via GH Actions job logs, `mcp__github__get_job_logs`) each showing `prompt_embeds_norm: 0.0` / `negative_prompt_embeds_norm: 0.0` at all 20 steps.
- Identical `latents_norm` trajectory (`261.8481750488281, 258.9233093261719, 255.7418212890625, ..., 158.408447265625, 165.33531188964844, 195.79042053222656`) across all 4 runs, byte-for-byte down to the printed float precision.
- Identical `video.mp4` size (20645 bytes) across all 4 runs.
- Direct re-check of iteration 0013's own locally-saved `metadata.json`: `prompt_embeds_norm: 41.77052688598633`, `negative_prompt_embeds_norm: 5.926913738250732` at every step - confirming these fields are capable of reporting real, nonzero, prompt-sensitive values when the underlying tensor genuinely isn't zero.
- Control run `30364516406` (0013's exact prompt, current commit): `prompt_embeds_norm: 0.0` - same prompt, same code, real vs. zero result differs by run, not by prompt.
- `git diff 8ba3653 c418e42 -- .../wan_inference.py`: confirmed read-only (prints + metadata fields only, no change to `resolved_prompt`, the `pipeline()` call, or any tensor mutation) - ruled out this session's own code edit as a plausible direct cause.

### 5. What was changed
No code changed this iteration beyond eval/reports/0014's already-committed GPU/torch/diffusers/dtype logging (`c418e42`), which is what let this iteration capture `gpu_name: "Tesla T4"` / `torch_version: "2.10.0+cu128"` / `diffusers_version: "0.37.1"` / `pipeline_dtype: "torch.bfloat16"` directly from all 4 runs - independently confirming eval/reports/0014's inference-from-source-code conclusion with hard, per-run evidence instead of a one-time read of `torch.cuda.is_bf16_supported()`'s source.

### 6. Before vs after comparison
| Run | Prompt (as actually received) | prompt_embeds_norm | video size | latents_norm end |
|---|---|---|---|---|
| 0013 (prior iteration, commit `8ba3653`) | "A cinematic sunset over a futuristic city, high quality" | **41.77** (real) | 21,736 bytes | 185.35 |
| 30360209748 | "A calm lake..." (unintended default) | **0.0** | 20,645 bytes | 195.79 |
| 30360289845 | "A red car" | **0.0** | 20,645 bytes | 195.79 |
| 30361353120 | "A snowy mountain at sunrise" | **0.0** | 20,645 bytes | 195.79 |
| 30364299854 | "A calm lake..." (space workaround also defaulted) | **0.0** | 20,645 bytes | 195.79 |
| 30364516406 (control, commit `c418e42`, 0013's own prompt) | "A cinematic sunset over a futuristic city, high quality" | **0.0** | 20,645 bytes | 195.79 |

### 7. Benchmark scores
Not applicable yet - the question this iteration answers is prerequisite to benchmarking (there is no point scoring 21 categories of prompts against an engine whose text conditioning may not be reaching the model at all).

### 8. Remaining weaknesses
- **The single most important open question in the whole investigation right now**: is the zero embedding a real bug in the text-encoding path, or an artifact of the `callback_on_step_end` + `enable_sequential_cpu_offload()` interaction? Section 3 above lays out both candidates honestly - neither is confirmed.
- A genuinely empty-prompt test still has not been run (both attempts - bare `""` and a single space `" "` - were silently replaced by the workflow's declared default by GitHub Actions itself, a real dispatch-level limitation, not a pipeline result).
- Video content still has not been visually re-confirmed for these 4 new runs (pending user upload, same as every prior iteration's discipline).

### 9. Next experiment
Isolate real-bug-vs-instrumentation-artifact directly, without going through another prompt A/B (that variable is now controlled-for and shown not to matter): add a *second*, independent print of the text encoder's output immediately inside `generate_video()`, computed directly (not via `callback_on_step_end`) right after `build_real_pipeline()` returns and before `pipeline(...)` is called - e.g. by calling `pipeline.encode_prompt(prompt=resolved_prompt, ...)` (or whatever WanPipeline's own internal encoding method is named) once, up front, and printing/logging its norm directly. If that direct call also reports zero, the bug is real and inside text encoding itself - the next step would be dumping the tokenizer's actual token IDs for the prompt to check for something degenerate (e.g. all-pad, an empty attention mask). If that direct call reports a real nonzero norm while the callback still reports 0.0 for the same run, the bug is confirmed to be in the diagnostic instrumentation (the `enable_sequential_cpu_offload()` race described in section 3) - meaning the transformer may have been receiving real conditioning all along, and the true root cause of the flat/muddy output remains open elsewhere. Also fix the empty-prompt dispatch limitation with a proper sentinel-based workaround for the next iteration that actually needs it.
