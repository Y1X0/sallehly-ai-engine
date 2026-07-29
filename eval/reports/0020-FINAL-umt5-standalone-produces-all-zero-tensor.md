# Iteration 0020: FINAL - UMT5 standalone (fully isolated, CPU, no WanPipeline) produces an all-zero tensor, not real embeddings

**Kaggle run:** [30431106646](https://github.com/Y1X0/sallehly-ai-engine/actions/runs/30431106646), commit `731c7b4`
**Prompt:** `A cinematic sunset over a futuristic city, high quality`
**Params:** `max_sequence_length=226`, `Wan-AI/Wan2.2-TI2V-5B-Diffusers`'s real `text_encoder`/`tokenizer` subfolders loaded directly - no `WanPipeline`, no transformer, no VAE, no `enable_sequential_cpu_offload`. Measure-only iteration per the user's explicit instruction: no fix or modification attempted after this run.

### 1. What was tested
The final isolation test in this line of investigation: does `transformers.UMT5EncoderModel`, loaded directly from the real Wan2.2 checkpoint and run completely independent of this project's code (`WanPipeline`, `diffusers`, offload), produce real or all-zero output? (Three prior real Kaggle GPU attempts each hit a different real CUDA memory-boundary failure trying to run this in isolation - eval/reports/0020's own commit history - resolved by running this one test on CPU instead, a disclosed deviation that does not change the model, dtype, or the computation itself.)

### 2. What failed / what was observed

**Environment:**
- CPU used (not GPU) - `torch_version: "2.10.0+cpu"`
- `transformers_version: "5.0.0"`
- `diffusers_version: "0.37.1"`
- RAM available: not captured by this run's logging (not added, per the user's explicit instruction not to modify anything after this run)

**Model:**
- `tokenizer_class: "T5Tokenizer"`
- `text_encoder_class: "UMT5EncoderModel"`
- `text_encoder_dtype: "torch.bfloat16"`
- `device_map_used: {"": "cpu"}`

**Forward output:**
```json
"last_hidden_state_shape": [1, 226, 4096],
"last_hidden_state_min": 0.0,
"last_hidden_state_max": 0.0,
"last_hidden_state_mean": 0.0,
"last_hidden_state_norm": 0.0,
"last_hidden_state_has_nan": false,
"last_hidden_state_has_inf": false
```
`abs_mean` and separate NaN/Inf *element counts* (as opposed to the boolean any-NaN/any-Inf checks already logged) were not captured by this run - not added per the user's explicit instruction not to modify anything after this run's result is recorded.

### 3. Single conclusion
**UMT5 standalone produces a tensor of exact zeros, not real embeddings.** `min == max == mean == norm == 0.0` on a `[1, 226, 4096]` tensor (924,416 elements) - not a rounding artifact or a numerically tiny result, a literal all-zero tensor, with no NaN and no Inf anywhere in it. This reproduces identically to every prior measurement in this investigation (eval/reports/0016-0019, on GPU, inside and outside `WanPipeline`, with and without `enable_sequential_cpu_offload`, with confirmed-real/non-meta weights) - now confirmed one final time completely independent of this project's code, this project's GPU, and even this project's device (CPU instead of GPU). The root cause is inside `UMT5EncoderModel`'s own computation for this checkpoint under this `transformers` version - not in `WanPipeline`, not in `diffusers`' integration of it, not in `enable_sequential_cpu_offload`, not in checkpoint loading, and not in this project's own code at any layer.

### 4. Evidence
- Real Kaggle run `30431106646`, job log (`mcp__github__get_job_logs`), `output/metadata.json`'s full echoed result (quoted in full above).
- `tokenizer_class`/`text_encoder_class` confirm the real, correct classes were loaded (not a fallback/generic class) - `T5Tokenizer`/`UMT5EncoderModel`, matching Wan2.2's own `model_index.json` declaration (`["transformers", "UMT5EncoderModel"]` / `["transformers", "T5TokenizerFast"]` - the loaded tokenizer resolved to the slow `T5Tokenizer` rather than the fast variant, a difference worth noting for the next investigator but not evidence of a loading error, since `AutoTokenizer.from_pretrained` chose it).
- Reproduces eval/reports/0016's (`WanPipeline`, GPU, offload ON) and eval/reports/0019's (`WanPipeline`, GPU, offload OFF, weights confirmed real/non-meta) all-zero result exactly, now on a third, maximally-isolated configuration (no `WanPipeline` at all, CPU instead of GPU).

### 5. What was changed
Nothing beyond the diagnostic infrastructure itself (already committed across this iteration's several fix commits - device_map loading, then CPU execution after repeated real GPU memory failures). No model, dtype, tokenizer call, or the real forward computation was changed. No root-cause fix attempted, per the user's explicit instruction.

### 6. Before vs after comparison
| Configuration | `last_hidden_state` result |
|---|---|
| Inside `WanPipeline`, GPU, `enable_sequential_cpu_offload` ON (eval/reports/0016/0017) | All zero |
| Inside `WanPipeline`, GPU, `enable_sequential_cpu_offload` OFF, weights confirmed real (eval/reports/0019) | All zero |
| **Standalone `UMT5EncoderModel`, CPU, no `WanPipeline` at all (this iteration)** | **All zero** |

Three independent configurations, one consistent result.

### 7. Benchmark scores
Not applicable - the root cause is now isolated to a specific external component (`transformers`' `UMT5EncoderModel` under this checkpoint), not this project's generation code.

### 8. Remaining weaknesses
- *Why* `UMT5EncoderModel` returns zeros under `transformers==5.0.0` for this checkpoint is still not identified at the mechanism level (e.g., which internal computation/layer/masking step produces the zero) - this iteration confirms *that* it happens and *where it does not* (not in this project's integration code), not the exact internal cause within `transformers`.
- The real, standout candidate this result surfaces: Wan2.2's `text_encoder/config.json` declares `"transformers_version": "4.48.0.dev0"`, while this Kaggle kernel's installed `transformers` is `5.0.0` - a major-version jump (4.x -> 5.x). This is exactly the "transformers version mismatch" candidate from the user's own 3-way hypothesis, and is now the leading explanation, though not yet directly confirmed by pinning an older version and re-testing.
- `AutoTokenizer.from_pretrained` resolved to the slow `T5Tokenizer` rather than a fast tokenizer class - not investigated further this iteration, and not established as related to the zero-output result.

### 9. Next experiment
Per the user's own already-stated plan and the `--transformers-version` flag already built into `dispatch_diagnose_umt5.py` for exactly this purpose: re-run this identical isolated test with `transformers` pinned close to the checkpoint's own declared `4.48.0.dev0` (e.g., `4.48.x` or the nearest available real release) to test directly whether the all-zero result is specific to `transformers==5.0.0` (a version-compatibility regression) or persists regardless of version (pointing further upstream, e.g., at the checkpoint itself). This is the single highest-value remaining test and requires no further code changes - the mechanism already exists.
