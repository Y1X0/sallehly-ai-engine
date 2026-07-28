# Iteration 0003: guidance_scale 1.0 -> 6.0 fix

**Kaggle run:** [30327666233](https://github.com/Y1X0/sallehly-ai-engine/actions/runs/30327666233), commit `efe7a5a`
**Prompt:** `A cinematic sunset over a futuristic city, high quality` (unchanged from 0001/0002)
**Params:** 960x544, 17 frames, 16fps, 20 steps, **guidance_scale=6.0** (was 1.0), seed=0 - single-variable change per §5

### 1. What was tested
Whether correcting `infra/kaggle/dispatch_inference.py`'s
`_DEFAULT_GUIDANCE_SCALE` from 1.0 to 6.0 (this engine's own
established, tested default for the Wan model family) fixes the
flat/muddy output seen in iterations 0001-0002.

### 2. What failed / what was observed
Job succeeded. Kernel duration was **1199s - about 26% longer than
iterations 0001/0002's 947-951s.** This is a real, measured compute-
time signal: classifier-free guidance requires a second (unconditional)
forward pass per denoising step, so a real activation of CFG
(guidance_scale > 1.0 crosses the `do_classifier_free_guidance`
threshold most diffusers pipelines use) should cost roughly double the
per-step compute - consistent with the observed duration increase.

However, `video.mp4` is **still exactly 127,355 bytes** - byte-for-byte
identical to iterations 0001 and 0002.

### 3. Root cause
**Unconfirmed - this is the open question, not yet resolved.** Two
readings are both consistent with current evidence and this report
does not pick one without pixel data:

- (a) `guidance_scale=6.0` changed the actual sampling computation (the
  duration increase supports this) but the *decoded frame content*
  still happens to compress to an identical byte count - possible if
  h264 rate control converges to the same size for two different but
  similarly low-entropy/low-detail images, though this would be an
  unusual coincidence to hit exactly, not approximately.
- (b) Something else prevents `guidance_scale` from affecting the
  actual pixel output at all despite the extra compute (e.g. a
  wiring bug elsewhere in the negative-prompt path, or the model
  requiring additional changes beyond `guidance_scale` alone) - not yet
  investigated because it requires the same pixel evidence as (a).

Per the mission's explicit rule ("never guess, support every
conclusion with evidence"), this iteration is left as **PENDING**
rather than forcing a conclusion neither reading is confirmed by yet.

### 4. Evidence
```
Kaggle job log:
  Kernel reached terminal status: complete (after 1199s)
  SUCCESS - real video written to .../video.mp4 (127355 bytes)
```
- Duration comparison: 951s (0001) / 947s (0002) / **1199s (0003)**.
- Artifact download attempted via `mcp__github__actions_get
  download_workflow_run_artifact` -> Azure Blob Storage URL
  (`productionresultssa14.blob.core.windows.net`) -> blocked by this
  sandbox's egress policy (same class of denial as two earlier
  artifacts on different `productionresultsSAxx` hosts - a confirmed,
  repeatable policy block, not a transient failure). Pixel-level
  verification requires the user to download the artifact from
  GitHub directly and share it back, as done for iteration 0001.

### 5. What was changed
`infra/kaggle/dispatch_inference.py`'s `_DEFAULT_GUIDANCE_SCALE`:
`1.0` -> `6.0`. No other parameter touched.

### 6. Before vs after comparison
| Metric | 0002 (guidance_scale=1.0) | 0003 (guidance_scale=6.0) |
|---|---|---|
| video.mp4 size | 127,355 bytes | 127,355 bytes (identical) |
| Kernel duration | 947s | **1199s (+26%)** |
| avg_stddev | inferred 9.21 (unconfirmed for 0002) | **not yet measured** |
| flat_frame_suspected | inferred true | **not yet measured** |

### 7. Benchmark scores
**Not scored - pixel verification pending.** Scoring without real
evidence would violate this project's own rule against guessing.

### 8. Remaining weaknesses
- Pixel-level verification of this run is the single blocking item
  before any further quality work can proceed with confidence.
- The sandbox's inability to download GitHub Actions artifacts directly
  (Azure Blob Storage egress is policy-blocked) is a recurring friction
  point for this whole loop - every iteration currently needs a manual
  user upload step to close the evidence loop.

### 9. Next experiment
Once the real video is available: run `eval/quality_metrics.py`
against it. If `flat_frame_suspected` is now `false` and content is
recognizable, guidance_scale=6.0 is confirmed as the fix and the loop
proceeds to running the full `eval/benchmark_prompts.yaml` suite
category by category. If it's still flagged flat, investigate reading
(b) above next - starting with whether `job_input["guidance_scale"]`
is actually reaching the real `pipeline()` call unmodified (add a
temporary debug print in `generate_video()` if needed).
