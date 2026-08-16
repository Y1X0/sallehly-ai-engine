# Iteration 0021: CONFIRMED - `transformers==4.48.0` produces real embeddings; `transformers==5.0.0` is the root cause

**Kaggle run:** [30432698242](https://github.com/Y1X0/sallehly-ai-engine/actions/runs/30432698242), job [90513322205](https://github.com/Y1X0/sallehly-ai-engine/actions/jobs/90513322205)
**Prompt:** `A cinematic sunset over a futuristic city, high quality`
**Params:** `max_sequence_length=226`, `Wan-AI/Wan2.2-TI2V-5B-Diffusers`'s real `text_encoder`/`tokenizer` subfolders loaded directly - identical script and config to eval/reports/0020, with exactly one variable changed: `transformers` pinned to `4.48.0` (installed via pip before any `transformers` import) instead of Kaggle's default `5.0.0`. Measure-only iteration per the user's explicit instruction: no fix or modification attempted after this run.

(Numbering note: the user's own instruction referred to this test as "iteration 0020," but `0020` was already used and committed for the prior CPU-standalone-at-`transformers==5.0.0` result. This report continues the log as `0021` to keep the numbering monotonic and avoid overwriting committed history.)

### 1. What was tested
The single remaining candidate from the user's own 3-way hypothesis after eval/reports/0016-0020: is the all-zero `UMT5EncoderModel` output specific to `transformers==5.0.0` (Kaggle's installed version), or does it persist regardless of version? One variable changed from iteration 0020: `transformers==4.48.0` (the version family Wan2.2's own `text_encoder/config.json` declares, `"transformers_version": "4.48.0.dev0"`) instead of `5.0.0`. Same checkpoint, same prompt, same tokenizer call, same CPU execution, same forward pass.

### 2. What was observed

**Environment:**
- CPU used (not GPU) - `torch_version: "2.10.0+cpu"`
- `transformers_version: "4.48.0"` (pinned, confirmed installed)
- `diffusers_version: "0.37.1"` (unchanged from iteration 0020)

**Model:**
- `tokenizer_class: "T5TokenizerFast"` (iteration 0020 resolved to the slow `T5Tokenizer`; under `4.48.0`, `AutoTokenizer.from_pretrained` resolved to the fast variant instead - not investigated further, not established as related to the result)
- `text_encoder_class: "UMT5EncoderModel"`
- `text_encoder_dtype: "torch.bfloat16"`
- `device_map_used: {"": "cpu"}`
- `input_ids_shape: [1, 226]`
- `attention_mask_sum: 14` (same real-token count as every prior iteration - tokenizer/mask unaffected by this change, as expected)

**Forward output:**
```json
"last_hidden_state_shape": [1, 226, 4096],
"last_hidden_state_min": -0.85546875,
"last_hidden_state_max": 0.94921875,
"last_hidden_state_mean": -0.0015001017600297928,
"last_hidden_state_std": 0.08284829556941986,
"last_hidden_state_norm": 79.72592163085938,
"last_hidden_state_has_nan": false,
"last_hidden_state_has_inf": false,
"last_hidden_state_nonzero_count": 925278
```
(925,696 total elements in the tensor; 925,278 nonzero - i.e. essentially every element is nonzero, consistent with a normal encoder output where only structural zeros, if any, would remain.)

### 3. Single conclusion
**`transformers==4.48.0` produces real, healthy embeddings from the exact same checkpoint, tokenizer call, and forward pass that produced an exact all-zero tensor under `transformers==5.0.0` in every prior iteration (0016-0020).** This is the decisive result: the root cause of the all-zero text conditioning that has affected every video generation since iteration 0001 is a `transformers` version incompatibility with this UMT5 checkpoint - specifically, whatever changed in `transformers` between `4.48.x` and `5.0.0` that affects `UMT5EncoderModel`'s forward computation for this checkpoint. It is not `WanPipeline`, not `diffusers`, not `enable_sequential_cpu_offload`, not checkpoint loading, and not any code in this project.

### 4. Evidence
- Real Kaggle run `30432698242`, job log (`mcp__github__get_job_logs`), full echoed `output/metadata.json` result (quoted in full above).
- One-variable-changed comparison against iteration 0020, same script, same commit's diagnostic code, same prompt/model/CPU execution.

### 5. What was changed
Nothing beyond the diagnostic infrastructure already committed (the `--transformers-version` pip-install-before-import mechanism, already built in iteration 0020's commit history). No model, dtype, tokenizer call, checkpoint, or the real forward computation was changed - only the `transformers` package version installed inside the isolated kernel. No project dependency files were touched. No fix attempted, per the user's explicit instruction not to move to any fix before this result is recorded.

### 6. Before vs after comparison
| Configuration | `transformers` | `last_hidden_state` result |
|---|---|---|
| Inside `WanPipeline`, GPU, offload ON (0016/0017) | 5.0.0 | All zero |
| Inside `WanPipeline`, GPU, offload OFF, weights confirmed real (0019) | 5.0.0 | All zero |
| Standalone `UMT5EncoderModel`, CPU, no `WanPipeline` (0020) | 5.0.0 | All zero (`min=max=mean=norm=0.0`) |
| **Standalone `UMT5EncoderModel`, CPU, no `WanPipeline` (this iteration)** | **4.48.0** | **Real (`norm=79.73`, `std=0.083`, 925,278/925,696 nonzero)** |

Four configurations, one variable changed in the fourth, one clean flip in result.

### 7. Benchmark scores
Not applicable - this is a text-encoder-output diagnostic, not a video-quality measurement. The actual video-quality benchmark (avg stddev threshold etc., per eval/REPORT_TEMPLATE.md) is deferred until a full `WanPipeline` run under a compatible `transformers` version is explicitly authorized and executed.

### 8. Remaining weaknesses
- *Why* `transformers==5.0.0` breaks `UMT5EncoderModel` for this checkpoint at the mechanism level (which internal computation, layer, or masking change between 4.48.x and 5.0.0 causes the zero output) is still not identified - this iteration confirms *that* the version is the cause, not the internal reason within `transformers`.
- This result is from the isolated standalone encoder test only. It has not yet been confirmed inside the real `WanPipeline` (i.e., pinning the project's own dependencies to a compatible `transformers` version and re-running a full video generation) - that is necessarily the next step, but is a separate, larger action (dependency changes + a full >1 hour Kaggle GPU run) that requires explicit user authorization before executing, per this investigation's established discipline.
- The tokenizer class resolving differently (`T5TokenizerFast` here vs. `T5Tokenizer` in iteration 0020) is noted but not investigated - not established as related to the root cause.
- The exact compatible version range for this project's other pinned dependency (`diffusers==0.37.1`, unchanged here) against `transformers==4.48.0` has not been verified beyond this one isolated encoder-only test - `WanPipeline`'s other components (transformer, VAE, scheduler) have not been exercised under this pin.

### 9. Next experiment
Per the user's own explicit instruction after this result: do not go fix the video directly. The first and only confirmed goal so far is that the text encoder can produce real embeddings under a compatible `transformers` version - this has now been demonstrated in isolation. The next step (pinning `transformers` in this project's actual dependencies and re-running a full `WanPipeline` video generation to confirm the fix holds end-to-end and produces real visual content) is a larger, separate action and awaits explicit user confirmation before being executed.
