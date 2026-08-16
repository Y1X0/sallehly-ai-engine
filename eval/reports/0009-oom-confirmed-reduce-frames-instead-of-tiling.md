# Iteration 0009: OOM confirms tiling was needed; reduce frame count instead

**Kaggle run:** [30347507026](https://github.com/Y1X0/sallehly-ai-engine/actions/runs/30347507026), commit `620198c`
**Prompt:** `A cinematic sunset over a futuristic city, high quality` (unchanged since 0001)
**Params:** 960x544, 17 frames, 16fps, 20 steps, guidance_scale=6.0, seed=42, VAE tiling disabled

### 1. What was tested
Whether disabling `pipeline.vae.enable_tiling()` (iteration 0008)
removes the checkerboard artifact identified by zooming into iteration
0007's frames.

### 2. What failed / what was observed
Real, exact OOM: `OutOfMemoryError: CUDA out of memory. Tried to
allocate 13.45 GiB. GPU 0 has a total capacity of 14.56 GiB of which
9.18 GiB is free.` - **identical to the original failure this exact
tiling fix resolved back in iteration 0002.** No video was produced.

### 3. Root cause
Confirmed, not merely suspected: VAE tiling is genuinely required for
memory at the current 17-frame/960x544 configuration on a 16GB T4 -
disabling it outright (0008) is not a viable fix on its own. The
checkerboard artifact (0007/0008) and the OOM (0002, reconfirmed here)
are two real, independent constraints pulling in opposite directions:
tiling avoids OOM but introduces the artifact; no tiling avoids the
artifact but reintroduces OOM.

The quantitative relationship is informative: 13.45 GiB / 17 frames ≈
0.79 GiB per frame for the single-shot (non-tiled) VAE decode
allocation. With 9.18 GiB free, reducing to 9 frames needs ≈7.1 GiB -
comfortably under budget with real margin, without touching tiling at
all.

### 4. Evidence
- Exact OOM error text and allocation size (13.45 GiB) - byte-for-byte
  identical to the error that originally motivated enabling tiling in
  iteration 0002, confirming this is the same constraint, not a new
  one.
- Kernel duration: 1011s before failing - shorter than successful runs
  (expected: it OOMs during decode, after the full 20-step denoising
  loop already ran to completion - the failure is specifically in the
  VAE decode stage, not the transformer).
- Simple arithmetic (13.45/17 GiB per frame) directly predicts a safe
  frame count without needing another blind trial-and-error OOM.

### 5. What was changed
No code change this iteration - `num_frames` is already a real,
existing dispatch parameter (`--num-frames`, exposed as a workflow
input). Reducing it from 17 to 9 for the next dispatch, VAE tiling
still disabled (0008's change stands).

### 6. Before vs after comparison
| Metric | 0008 (17 frames, no tiling) | 0009 (9 frames, no tiling) |
|---|---|---|
| VAE decode allocation needed | 13.45 GiB (OOM) | ≈7.1 GiB (predicted, pending confirmation) |
| Free memory | 9.18 GiB | 9.18 GiB (unchanged) |
| Checkerboard risk | none (tiling off) | none (tiling off) |

### 7. Benchmark scores
Not applicable - no video was produced this iteration (OOM before decode completed).

### 8. Remaining weaknesses
- A shorter clip (9 frames, ~0.56s @ 16fps) is a real trade-off against
  this investigation's own quality goals - acceptable short-term to
  confirm the checkerboard hypothesis cleanly, not a permanent
  target. Once confirmed real content is possible without tiling,
  revisit whether correctly-tuned tiling parameters
  (`tile_sample_min_height`/`width`, `tile_sample_stride_height`/`width`
  - `AutoencoderKLWan.enable_tiling()` accepts explicit overrides
  instead of only its class defaults) could restore 17+ frames without
  the artifact, rather than permanently shrinking clip length.

### 9. Next experiment
Dispatch with `num_frames=9`, VAE tiling still disabled, everything
else unchanged (seed=42, guidance_scale=6.0). If successful and visual
inspection shows real, recognizable content with no checkerboard: this
confirms both hypotheses at once (tiling caused the artifact; frame
count was the memory lever, not tiling). If checkerboard is still
present even without tiling and without OOM: the artifact is not
tiling-related at all, and the transformer's patchify/unpatchify path
needs direct investigation next.
