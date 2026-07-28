# Iteration 0014: Visual check on 0013's video + the dtype confound resolved (not just flagged)

**Same Kaggle run as 0013:** [30355470112](https://github.com/Y1X0/sallehly-ai-engine/actions/runs/30355470112), commit `8ba3653`
**No new Kaggle run this iteration** - this is direct analysis of the artifact already downloaded for 0013 (`output/video.mp4`, `output/metadata.json`), plus a real, local, evidence-based resolution of the dtype question left open in 0013.

### 1. What was tested
Two things, both diagnostic-only (no code changed):
1. Whether the vertical blend-seam banding from iteration 0012 is actually gone in 0013's single-tile-decode video, and whether real, recognizable content ("cinematic sunset over a futuristic city") is present - by running `eval/quality_metrics.py` on the real downloaded `video.mp4` and directly viewing extracted frames.
2. Whether the `bfloat16` dtype logged in 0013 is really a new/uncontrolled variable versus 0011/0012 (as 0013 flagged), by reading the real, installed `torch.cuda.is_bf16_supported()` source directly instead of continuing to guess.

### 2. What failed / what was observed

**(a) Visual check: banding is gone, but the core problem is not fixed.**
`eval/quality_metrics.py` on the real video:
```
avg_stddev: 8.84
flat_frame_suspected: true
flat_frame_stddev_threshold: 20.0
WARNING: avg per-frame stddev 8.84 is below 20.0 - this looks like the
known flat/muddy failure mode, not real rendered content.
```
Direct frame extraction (`ffmpeg -vf select=...`) and visual inspection of
4 sampled frames (t=0, 0.138s, 0.276s, 0.413s) confirms this numerically:
all four are a flat lavender/purple field with soft, low-contrast blotches
and no recognizable subject, skyline, horizon, or lighting structure - a
sunset over a futuristic city is not present. **However, the hard vertical
banding seams visible in 0012's frames are genuinely gone** - the single-
tile decode fix did remove that specific artifact. This is real, if
partial, progress: one visual defect (tile-blend seams) is eliminated;
the deeper defect (no image content forming at all) remains.

**(b) The dtype confound is resolved, not just flagged - and the answer changes the story.**
0013 flagged `bfloat16` (vs. the assumed-but-unconfirmed `fp16`) as an
uncontrolled variable. Read directly from a real, currently-installed
`torch` (2.13.0+cu130, via ephemeral `uv run --with torch` - not Kaggle's
exact build, but a materially identical, modern torch release):
```python
def is_bf16_supported(including_emulation: bool = True):
    if torch.version.hip:
        return True
    if not is_available():
        return False
    device = torch.cuda.current_device()
    if torch.cuda.get_device_properties(device).major >= 8:
        return True
    if not including_emulation:
        return False
    return _check_bf16_tensor_supported(device)

@lru_cache(maxsize=16)
def _check_bf16_tensor_supported(device):
    try:
        torch.tensor([1.0], dtype=torch.bfloat16, device=device)
        return True
    except Exception:
        return False
```
T4 is compute capability 7.5 (`major == 7`), so it fails the `>= 8` fast
path - but falls through to `_check_bf16_tensor_supported`, which just
tries to allocate a `bfloat16` tensor on the device. This trivially
succeeds on any modern CUDA build (bf16 storage/compute has been
supported via software path since well before Turing/T4) - so
`is_bf16_supported()` returns **`True` on a T4** with this (and almost
certainly any recent) torch version. `including_emulation` defaults to
`True` - the code never had to opt in to this.

### 3. Root cause
**The dtype was almost certainly `bfloat16`, not `fp16`, in every single
iteration of this investigation (0001-0013), not just 0013.** The
`wan_inference.py` dtype-selection code (`build_real_pipeline`) has
always called exactly this `is_bf16_supported()` function with no
version pin or override, and nothing changed that check between
iterations - so there is no reason 0011/0012 would have evaluated it
differently than 0013 did. The "T4 has no bf16 tensor-core support, so
we fall back to fp16" comment in the code (and this investigation's own
working assumption since iteration 0001) is not what actually happens at
runtime: `is_bf16_supported()` measures *software* bf16 support, not
*tensor-core-accelerated* bf16 support, and the former is present on T4.

**This retroactively re-explains, rather than contradicts, the earlier
"fp16 ruled out" findings from iterations 0002/0005/0006:** those
iterations upcast `vae`/`text_encoder`/`transformer` to `fp32` *only
inside an `if pipeline_dtype == torch.float16:` guard*. If
`pipeline_dtype` was actually `bfloat16` all along, that guard never
matched, and the fp32-upcast code never ran in any of those iterations.
Their "zero measurable effect" result is exactly what a dead code path
would produce - it does not mean fp16 overflow was tested and excluded;
it means fp16 was likely never the active dtype to begin with, so there
was nothing for the upcast to fix. **Fp16-overflow-as-root-cause was
never actually falsified by those iterations - it was never on the
execution path in the first place.**

### 4. Evidence
- `eval/quality_metrics.py` output on iteration 0013's real `video.mp4`: `avg_stddev: 8.84` (threshold 20.0), `flat_frame_suspected: true`.
- 4 directly-viewed extracted frames (t=0/0.138/0.276/0.413s): flat purple/lavender fields, no recognizable content, no hard banding lines (unlike 0012's frames).
- Real `torch.cuda.is_bf16_supported` and `_check_bf16_tensor_supported` source, read directly from an installed torch 2.13.0+cu130 via `uv run --with torch`.
- `output/metadata.json` from run 30355470112: `transformer_dtype`/`vae_dtype`/`text_encoder_dtype` all `"torch.bfloat16"`, `latents_dtype` logged as `"torch.float32"` at every step (latents themselves are kept in fp32 by the scheduler regardless of model weight dtype - a separate, expected detail, not a contradiction).

### 5. What was changed
Nothing in code this iteration - pure diagnostic analysis of already-collected data (the 0013 artifact) plus a real source-code read of installed `torch`. No Kaggle run was needed to reach this conclusion.

### 6. Before vs after comparison
| Question | Status before this iteration | Status after |
|---|---|---|
| Is the 0012 vertical banding gone in 0013? | Unconfirmed (numbers only) | **Confirmed gone** - visually clean, no hard seams |
| Is real, recognizable content present in 0013? | Unconfirmed | **Confirmed absent** - flat, low-variance (stddev 8.84), no subject/skyline |
| Was 0011/0012's dtype fp16 or bf16? | Unknown, assumed fp16 | **Resolved: almost certainly bf16**, same as 0013, via direct source evidence |
| Does the "fp16 ruled out" conclusion (0002/0005/0006) still hold? | Assumed yes | **Reframed**: those fixes likely never executed (dead `if pipeline_dtype == torch.float16` branch); fp16-as-cause was never actually tested, not disproven |

### 7. Benchmark scores
Not applicable - output still fails the basic "is there any real image content" gate; scoring the 21-category benchmark against flat noise would not be meaningful yet.

### 8. Remaining weaknesses
- The actual root cause of the flat/muddy output (present since iteration 0001, now confirmed to persist under bf16, single-tile decode, correct guidance_scale=6.0, seed=42, and a numerically stable/finite latent trajectory) is **still unknown**. Every hypothesis tested so far (fp16 overflow in three submodules, seed, VAE tiling on/off, tile count) has been individually ruled out or shown not to be the (sole) explanation.
- Per the user's own prioritized diagnostic plan, the untested items that now matter most are: (1) an empty-prompt vs. simple-prompt A/B to isolate whether text conditioning is reaching the transformer at all, (2) checking latent shape divisibility (`[1, 48, 3, 16, 30]` at 480x272/9 frames) against the model's expected patch/downsample factors, (3) comparing directly against the official Wan2.2 example config/resolution, (4) a torch/diffusers/transformers/accelerate/safetensors version compatibility check.
- Should also directly confirm (next Kaggle run, one line of logging) `torch.__version__` and `torch.cuda.get_device_name(0)` to nail down exactly which GPU/torch build Kaggle assigns - closing this out with direct evidence rather than a same-code-path inference, even though the inference here is strong.

### 9. Next experiment
Add one cheap, high-value logging line to `wan_inference.py` (`torch.__version__`, `torch.cuda.get_device_name(0)`, `torch.cuda.get_device_capability(0)`) so the next real Kaggle run settles the GPU/torch-version question with direct evidence instead of inference. Then run the empty-prompt vs. simple-prompt A/B test (user's diagnostic plan item #4) - this is the highest-value remaining test because it directly checks whether text conditioning reaches the transformer, which would explain a flat, content-less-but-numerically-stable output better than anything ruled out so far.
