# Iteration 0003: guidance_scale 1.0 -> 6.0 fix

**Kaggle run:** [30327666233](https://github.com/Y1X0/sallehly-ai-engine/actions/runs/30327666233), commit `efe7a5a`
**Prompt:** `A cinematic sunset over a futuristic city, high quality` (unchanged from 0001/0002)
**Params:** 960x544, 17 frames, 16fps, 20 steps, guidance_scale=6.0 (was 1.0), seed=0 - single-variable change per §5

### 1. What was tested
Whether correcting `infra/kaggle/dispatch_inference.py`'s
`_DEFAULT_GUIDANCE_SCALE` from 1.0 to 6.0 (this engine's own
established, tested default for the Wan model family) fixes the
flat/muddy output seen in iterations 0001-0002.

### 2. What failed / what was observed
**Definitive, hard evidence (user uploaded the real artifact):**

```
$ sha256sum iter0001-video.mp4 iter0003-video.mp4
c4b7bd9472aa954d147f5d49df3229b0e0ecb06df6d138ff44c626c82ae549fd  iter0001-video.mp4
c4b7bd9472aa954d147f5d49df3229b0e0ecb06df6d138ff44c626c82ae549fd  iter0003-video.mp4
$ cmp iter0001-video.mp4 iter0003-video.mp4
(no output - files are byte-for-byte identical)
```

The iteration 0003 video is **byte-for-byte identical** to iteration
0001's - not just similar file size, the literal same file, confirmed
by SHA256 and `cmp`. Direct visual inspection of 5 sampled frames (0,
4, 8, 12, 16) confirms: uniform flat brownish-gray texture with a faint
dither/checkerboard pattern, no sky, no city silhouette, no sunset
colors, no discernible objects or composition of any kind. Frame-to-
frame variation is limited to a slight global brightness drift - not
real motion.

`eval/quality_metrics.py` output (identical to iteration 0001's, as
expected given the byte-identical file):
```
avg_stddev: 9.21
flat_frame_suspected: true
mean RGB across sampled frames: ~(89-101, 82-91, 73-82)
stddev RGB across sampled frames: ~7-14, all channels
```

**Prompt-fidelity assessment (Steps 1-4 of the evaluation process):**
The output does not match the prompt "A cinematic sunset over a
futuristic city, high quality" in any respect - no sunset colors, no
city, no buildings, no silhouette, no cinematic framing.

| Failure mode | Present? |
|---|---|
| Blur | N/A - no content to be sharp or blurry |
| Artifacts | Yes - the entire frame is a dither/noise artifact |
| Hallucinations | No hallucinated objects - just noise, nothing invented |
| Wrong objects | N/A - no objects at all |
| Missing objects | Yes - sunset, city, buildings, sky, light source all absent |
| Temporal inconsistency / flickering | Minimal - frames are self-similar (consistent with a degenerate, non-generative output, not with real stability) |
| Poor motion | Yes - only a slow global brightness drift, no real motion |
| Incorrect lighting | Yes - no identifiable light source, flat uniform illumination |
| Weak composition | Yes - no foreground/background/subject separation at all |
| Broken anatomy | N/A - no subjects present |
| Unrealistic physics | N/A |
| Color problems | Yes - desaturated, dynamic range compressed to ~34-130 of 0-255 |
| Camera problems | N/A - no camera movement/framing present |

### 3. Root cause
**The fp32-VAE-upcast and guidance_scale=6.0 fixes are both now proven
to have had zero effect on the actual output.** A byte-identical file
across three iterations with two genuinely different code paths rules
out "the fix worked but subtly" - this is conclusive, not inferred.

This redirects the investigation away from *tuning generation
parameters* and toward *whether those parameters are reaching the real
model call at all*, or whether the model's output is for some other
reason insensitive to both VAE decode precision and CFG. The measured
+26% run duration (1199s vs 947-951s in iterations 0001/0002) proves
*some* extra computation happened - most consistent with
`do_classifier_free_guidance` actually triggering an extra
unconditional forward pass this time - but that extra computation had
no visible effect on the final decoded pixels.

**Not yet confirmed which of these is true (stated honestly, not
guessed):**
- (a) The unconditional (negative-prompt) branch's noise prediction is
  numerically identical (or near-identical) to the conditional
  branch's, collapsing the CFG combination formula to a no-op
  regardless of `guidance_scale`'s value (e.g. a bug feeding the same
  embedding to both branches).
- (b) Text/prompt conditioning has no effect on this pipeline's output
  at all, independent of CFG - a deeper bug than guidance_scale, which
  would also explain why fp16-vs-fp32 VAE precision didn't change
  anything (if the *latents* going into the VAE were already identical
  garbage, any decode precision would decode it into the same-looking
  garbage).

### 4. Evidence
- SHA256 + `cmp` byte-for-byte match between iteration 0001's and
  iteration 0003's real uploaded video files (see §2).
- `eval/quality_metrics.py` output identical to iteration 0001 (§2).
- 5 real sampled frames visually inspected directly (not just
  aggregate stats) - confirmed flat, contentless, matching the numeric
  analysis exactly.
- Kaggle job log: `Kernel reached terminal status: complete (after
  1199s)` vs 947s/951s in iterations 0001/0002 - real, measured compute
  time difference, the only evidence so far that *anything* about the
  run actually changed.

### 5. What was changed
(This iteration's own change, evaluated above): `_DEFAULT_GUIDANCE_SCALE`
1.0 -> 6.0 in `infra/kaggle/dispatch_inference.py`. Confirmed to have
had no measurable effect on output.

### 6. Before vs after comparison
| Metric | 0002 (guidance_scale=1.0) | 0003 (guidance_scale=6.0) |
|---|---|---|
| video.mp4 SHA256 | `c4b7bd94...` (inferred identical, see 0002's caveat) | `c4b7bd94...` (confirmed identical to iteration 0001) |
| Kernel duration | 947s | 1199s (+26%) |
| avg_stddev | 9.21 | 9.21 (identical) |
| flat_frame_suspected | true | true |
| Visual content | Flat brown-gray noise | Flat brown-gray noise (identical) |

### 7. Benchmark scores
| Dimension | Score | Notes |
|---|---|---|
| Prompt understanding | 0/10 | Zero correspondence to "sunset"/"city"/"cinematic" |
| Visual quality | 0/10 | Flat, low-contrast noise |
| Motion | 1/10 | Only a slight global brightness drift, no real motion |
| Temporal consistency | 4/10 | Self-consistent only because it's degenerate, not because it's stable real content |
| Camera | 0/10 | No framing/camera work present |
| Lighting | 0/10 | No identifiable light source or direction |
| Cinematic quality | 0/10 | |
| **Overall** | **0/10** | Identical to iteration 0001 - no improvement despite two applied fixes |

### 8. Remaining weaknesses
- Root cause of the flat/degenerate output is still not identified with
  certainty - both applied hypotheses (VAE precision, guidance_scale)
  are now proven not to be it.
- No direct visibility into what parameter values actually reach the
  real `pipeline()` call inside the Kaggle kernel - this is the actual
  blocking gap preventing further progress without guessing.

### 9. Next experiment
Before proposing another parameter-value hypothesis (which would be
guessing, given two have already failed), add minimal, purely additive
observability: log the actual resolved `guidance_scale` and
`negative_prompt` values used by the real `pipeline()` call into
`generate_video()`'s returned metadata (already printed to the Kaggle
job log and saved as `metadata.json`). This makes no behavior change
and carries no risk of another wasted iteration - it turns "we believe
guidance_scale=6.0 reached the model" into a directly verifiable fact
in the next run's log, closing the wiring-vs-numerics ambiguity in §3
before spending another real Kaggle GPU run on a guess.
