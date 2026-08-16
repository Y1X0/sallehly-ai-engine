# Iteration 0010: Frame-reduction hypothesis disproven; investigation paused

**Kaggle run:** [30350022199](https://github.com/Y1X0/sallehly-ai-engine/actions/runs/30350022199), commit `5b46804`
**Prompt:** `A cinematic sunset over a futuristic city, high quality` (unchanged since 0001)
**Params:** 960x544, **9 frames** (was 17), 16fps, 20 steps, guidance_scale=6.0, seed=42, VAE tiling disabled

### 1. What was tested
Whether reducing `num_frames` from 17 to 9 (a linear-scaling estimate
from 0009: 13.45 GiB / 17 frames ≈ 0.79 GiB/frame, so 9 frames should
need ≈7.1 GiB, fitting the 9.18 GiB free) allows a real, non-tiled VAE
decode without OOM.

### 2. What failed / what was observed
**The estimate was wrong.** With 9 frames instead of 17, the error is:
```
OutOfMemoryError: CUDA out of memory. Tried to allocate 13.45 GiB.
GPU 0 has a total capacity of 14.56 GiB of which 8.35 GiB is free.
```
**The identical 13.45 GiB allocation size as the 17-frame failure
(iteration 0008)** - not scaled down at all. This disproves 0009's
core assumption that this allocation scales linearly (or at all) with
`num_frames`.

### 3. Root cause
**Still not identified.** The 0009 hypothesis (VAE decode memory
scales with frame count) is now falsified by direct evidence: the
exact same 13.45 GiB allocation occurs regardless of whether 17 or 9
frames are requested. This means the allocation is not primarily
about decoding N frames of pixel data - it's something with a fixed
size independent of frame count, most likely tied to spatial
resolution (960x544, unchanged across both tests) rather than
temporal length. This echoes an even earlier observation in this
project's history (`build_real_pipeline`'s own docstring, from before
sequential offload existed): "byte-identical numbers regardless of
num_frames (17 vs 9)... proves the ceiling is the resident pipeline's
own weight footprint, not per-step activation memory that scales with
frame count" - a similar frame-count-independent pattern was already
seen once before in a different context, and this iteration
rediscovers the same shape of surprise in the VAE-decode-without-tiling
case specifically.

### 4. Evidence
- Exact OOM allocation size: 13.45 GiB, identical between 17-frame
  (0008) and 9-frame (0010) attempts - the single, decisive piece of
  evidence this report is built on.
- Free memory differed slightly (9.18 GiB in 0008 vs 8.35 GiB in
  0010 - real-world Kaggle instance variance), but the *requested*
  allocation was identical, which is what actually matters here.
- Kernel duration: 830s before failing (vs 1011s for the 17-frame
  attempt) - shorter, consistent with less time spent in the
  transformer's denoising loop for fewer frames, even though the final
  failing allocation size didn't change.

### 5. What was changed
`num_frames` 17 -> 9 for this dispatch only (workflow input, no code
change). Confirmed ineffective at avoiding the OOM.

### 6. Investigation paused here, per explicit user request

The user asked to stop actively debugging this ("زهقت" - tired of it).
Per that request, no further Kaggle runs are being launched
automatically. This report captures the state honestly for whenever
work resumes:

**What is confirmed, real, and fixed in this investigation:**
- Kaggle GPU dispatch/fetch pipeline works end-to-end (T4 pinning, auth, dataset upload, kernel polling) - solid since early iterations.
- `guidance_scale` default corrected from 1.0 to 6.0 (this engine's real, tested default) - a genuine, real fix, independent of everything below.
- `step_latent_norms` diagnostic and configurable `seed`/`prompt`/`negative_prompt` echo in metadata - real, useful, permanent observability additions.
- fp16 numerical overflow was directly and individually ruled out in the VAE, text encoder, and transformer (all upcast to fp32, all tested, all confirmed not the cause of the earlier flat/muddy output).
- The flat/muddy output across iterations 0001-0007 is now understood to be a checkerboard/tiling-blend artifact (confirmed by zooming into frames), not a precision or conditioning bug.

**What is NOT yet resolved:**
- A real trade-off between two constraints: `enable_tiling()` avoids a 13.45 GiB single-allocation OOM but introduces a visible checkerboard artifact; disabling it removes the artifact risk but reintroduces the identical-sized OOM **regardless of frame count** (this iteration's finding) - meaning frame-count reduction is not the lever that controls this specific allocation.
- The actual mechanism producing the 13.45 GiB allocation is unidentified - it does not scale with `num_frames`, so it is most likely tied to spatial resolution (960x544) or a fixed intermediate buffer somewhere in the VAE decode path, not per-frame decode cost as assumed in iteration 0009.

### 7-9. Not applicable this iteration
No video was produced; no benchmark scores, before/after comparison,
or next single experiment are proposed here since the investigation is
intentionally paused rather than continuing to the next hypothesis.
When resumed, the natural next test (not yet run) would be reducing
*resolution* rather than frame count, since this iteration's evidence
points toward the allocation being resolution-dependent, not
frame-count-dependent.
