# Iteration 0001: First real video, fp16 VAE decode

**Kaggle run:** [30303715804](https://github.com/Y1X0/sallehly-ai-engine/actions/runs/30303715804), commit `d2e26d8`
**Prompt:** `A cinematic sunset over a futuristic city, high quality`
**Params:** 960x544, num_frames=17, fps=16, sampling_steps=20, guidance_scale=1.0 (see iteration 0003 for why this default was wrong), seed=0

### 1. What was tested
First real, full-scale Wan2.2-TI2V-5B generation to complete on a real
Kaggle T4 without crashing, after several earlier iterations fixing
OOM/CUDA-architecture issues (see CHANGELOG / commit history:
`enable_model_cpu_offload` -> fp16 fallback -> T4 pinning ->
`enable_sequential_cpu_offload`/`enable_attention_slicing` ->
`vae.enable_tiling`/`enable_slicing`).

### 2. What failed / what was observed
Job completed with `conclusion: success`, wrote a real, correctly-sized
`video.mp4` (127,355 bytes, 17 frames @ 960x544 @ 16fps - matches the
requested params exactly). But every sampled frame is near-flat, muddy,
and desaturated instead of showing the requested scene.

### 3. Root cause
Decoding the VAE in fp16 overflows its narrow exponent range inside
GroupNorm/attention layers - a well-documented Stable-Diffusion-family
failure mode. fp16 was forced because this GPU (T4) lacks bf16
tensor-core support (`torch.cuda.is_bf16_supported()` is `False`).

**Correction from iteration 0003: this diagnosis was wrong** - see
0002/0003. The real cause was `guidance_scale=1.0`, unrelated to VAE
precision. Left here unedited per this log's own rule (evidence
supported this conclusion at the time; the next iteration disproved it).

### 4. Evidence
```
$ uv run python eval/quality_metrics.py video.mp4 --num-samples 4
avg_stddev: 9.21
flat_frame_suspected: true
per-frame mean RGB: ~(90-101, 82-91, 73-82) across all 4 samples
per-frame stddev RGB: ~8-14 across all 4 samples, all channels
```
(Video obtained via user upload - direct artifact download from this
sandbox is blocked by network egress policy, see infra notes.)

### 5. What was changed
Upcast `pipeline.vae` to `torch.float32` after loading (keeping
transformer/text-encoder in fp16) - the diffusers/SDXL-idiomatic "just
upcast the VAE" fix for fp16 decode overflow.

### 6. Before vs after comparison
See iteration 0002 - the fix produced a byte-identical file, i.e. no
measurable change.

### 7. Benchmark scores
| Dimension | Score | Notes |
|---|---|---|
| Prompt understanding | 0/10 | No recognizable scene content |
| Object correctness | 0/10 | No discernible objects |
| Scene correctness | 0/10 | No discernible scene |
| Cinematic quality | 0/10 | Flat noise, no framing/lighting design |
| Motion quality | N/A | Can't assess motion with no visible content |
| Lighting | 0/10 | Compressed to a narrow, muddy brown-gray range |
| Camera movement | N/A | Not assessable |
| Realism | 0/10 | |
| Consistency | 3/10 | Frames are at least self-consistent with each other (all equally flat) |
| Flickering | 8/10 | Little frame-to-frame variation, but that's a symptom of the failure, not real stability |
| Temporal coherence | N/A | Not meaningfully assessable |
| Subject identity | N/A | No subject present |
| Composition | 0/10 | |
| Color grading | 0/10 | Desaturated, compressed dynamic range |
| Artifacts | 2/10 | The entire frame is the artifact |
| **Overall** | **0/10** | Real crash-free pipeline execution, zero usable visual output |

### 8. Remaining weaknesses
- No real content whatsoever - this is the blocking issue, nothing else can be evaluated until it's fixed.

### 9. Next experiment
Test whether upcasting the VAE to fp32 (isolated, single-variable
change) fixes the flat output - see iteration 0002.
