# Iteration 0004: Confirm guidance_scale wiring via metadata echo; trace real diffusers source for the actual root cause

**Kaggle run:** [30331749263](https://github.com/Y1X0/sallehly-ai-engine/actions/runs/30331749263), commit `e063bca`
**Prompt:** `A cinematic sunset over a futuristic city, high quality` (unchanged from 0001-0003)
**Params:** 960x544, 17 frames, 16fps, 20 steps, guidance_scale=6.0, seed=0 - diagnostic-only change per §5 (no generation behavior touched)

### 1. What was tested
Whether `guidance_scale=6.0` (and the real prompt/negative_prompt)
actually reach the real `pipeline()` call inside the Kaggle kernel, by
echoing those exact resolved values into `generate_video()`'s returned
metadata (printed to every job log as `metadata.json`).

### 2. What failed / what was observed
The printed metadata **confirms the wiring is correct**:
```json
{
  "prompt": "A cinematic sunset over a futuristic city, high quality",
  "negative_prompt": null,
  "guidance_scale": 6.0
}
```
`guidance_scale=6.0` genuinely reaches `pipeline()`. The run also took
**1311s - longer than iteration 0003's 1199s, both far longer than
iterations 0001/0002's 947-951s** - real, repeated evidence that real
extra computation happens when `guidance_scale > 1.0`.

`video.mp4` is still exactly **127,355 bytes** - the same size as all
three prior iterations (not yet re-confirmed by SHA256 for this
specific run pending a fresh upload, but this is the 4th consecutive
occurrence of the identical byte count, now backed by confirmed-correct
parameter wiring, which rules out the wiring-bug hypothesis entirely).

### 3. Root cause
**Traced directly in the real installed `diffusers` source
(`diffusers.pipelines.wan.pipeline_wan.WanPipeline`), not guessed:**

- `do_classifier_free_guidance` is exactly `self._guidance_scale > 1.0`
  - confirmed `True` for our `guidance_scale=6.0`.
- The CFG combination is the textbook-correct formula:
  ```python
  noise_pred = noise_uncond + current_guidance_scale * (noise_pred - noise_uncond)
  ```
- `encode_prompt()` correctly falls back `negative_prompt = negative_prompt or ""`
  when `negative_prompt=None` (our case), then encodes that empty
  string through `_get_t5_prompt_embeds()` - the **same** T5 encoder
  used for the real positive prompt, just with different input text.

All of this is standard, correct, unmodified diffusers code - **not a
bug in this codebase's wiring.** For the final output to stay
byte-identical despite a real extra forward pass, `noise_uncond` must
equal (or nearly equal) `noise_pred` at every step, which only happens
if the *positive* and *empty-string* prompt embeddings themselves come
out numerically similar/degenerate - i.e. the text encoder's output
carries little to no real information about the input text at all.

**Working hypothesis (not yet confirmed - stated as a hypothesis, not
a conclusion):** `UMT5EncoderModel` (the text encoder) is never
upcast to fp32 anywhere in this codebase - only `pipeline.vae` was
(iteration 0002's fix). T5-family encoders are a well-documented case
of fp16 numerical instability (external, widely-reported issue, not
specific to this codebase) - the same overflow failure mode already
found and fixed once for the VAE (iteration 0001-0002) could equally
be happening in the text encoder, which would make both the
conditional and unconditional embeddings collapse toward the same
degenerate values regardless of input text - explaining every piece of
evidence gathered so far: the muddy/flat output since iteration 0001,
its complete insensitivity to VAE precision (garbage in, garbage out
regardless of decode precision) and to guidance_scale (CFG becomes a
no-op if both branches' conditioning is equally degenerate).

### 4. Evidence
- Kaggle job log's printed `metadata.json` (quoted in full above).
- Job durations across all 4 iterations: 951s / 947s / 1199s / **1311s**
  - monotonically longer whenever `guidance_scale > 1.0`, consistent
    with the `do_classifier_free_guidance` code path genuinely
    executing.
- Direct inspection of the installed `diffusers` package's
  `WanPipeline.__call__`, `.do_classifier_free_guidance`,
  `.encode_prompt`, and `._get_t5_prompt_embeds` source (see command
  log: `uv run --with diffusers --with torch --with transformers
  python3 -c "import inspect; ..."`), confirming the CFG mechanism
  itself is standard/correct diffusers code.
- `_get_t5_prompt_embeds`'s own dtype handling:
  `dtype = dtype or self.text_encoder.dtype` - confirms the text
  encoder's dtype directly controls the precision the real T5 forward
  pass runs at, exactly mirroring the VAE's dtype-propagation pattern
  already fixed in iteration 0002.

### 5. What was changed
This iteration: purely additive observability (metadata echo, commit
`e063bca`) - no generation behavior was touched. The next iteration
(0005) will test the text-encoder-upcast hypothesis above as its own,
separate, single-variable change.

### 6. Before vs after comparison
| Metric | 0001 | 0002 | 0003 | 0004 |
|---|---|---|---|---|
| guidance_scale | 1.0 | 1.0 | 6.0 | 6.0 |
| video.mp4 size | 127,355 | 127,355 | 127,355 | 127,355 |
| Kernel duration | 951s | 947s | 1199s | **1311s** |
| Confirmed wiring | n/a | n/a | inferred | **confirmed via metadata.json** |

### 7. Benchmark scores
Unchanged from iterations 0001/0003 (0/10 overall) - no code change
that could affect pixels was made this iteration.

### 8. Remaining weaknesses
- Root cause is now narrowed to "the text encoder's fp16 output is
  likely degenerate/input-insensitive" but this is still a hypothesis,
  not a confirmed fact - it must be tested with an isolated,
  single-variable change (§9), not assumed.
- No visibility yet into the actual embedding tensors themselves
  (e.g. their norm/variance) - if the text-encoder-upcast experiment
  in 0005 also fails to change the output, that would be strong
  evidence to add that kind of direct tensor-statistics logging next.

### 9. Next experiment
Upcast `pipeline.text_encoder` to `torch.float32` (same `if
pipeline_dtype == torch.float16:` block that already upcasts the VAE),
keeping the transformer in fp16 for memory. `_get_t5_prompt_embeds`
already casts its output back to the transformer's dtype at the end,
so this only changes the precision of the *encoder's own internal
computation*, not memory footprint downstream - the same
"upcast-just-the-vulnerable-submodule" pattern already validated for
the VAE in iteration 0002 (which, notably, had no effect on output -
underscoring that this hypothesis must be verified against a real run,
not assumed to work just because the pattern matches).
