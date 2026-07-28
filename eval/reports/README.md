# Quality iteration log

Running, chronological log of every real Kaggle GPU generation used to
evaluate or improve output quality, per `eval/REPORT_TEMPLATE.md`. One
file per iteration, numbered in run order. Never edited after the fact
except to append new evidence - if a conclusion turns out wrong, the
next iteration says so explicitly rather than rewriting history.

| # | Title | Kaggle run | Verdict |
|---|---|---|---|
| 0001 | First real video, fp16 VAE decode | [30303715804](https://github.com/Y1X0/sallehly-ai-engine/actions/runs/30303715804) | FAIL - flat/muddy garbage frames |
| 0002 | fp32 VAE upcast fix | [30316220351](https://github.com/Y1X0/sallehly-ai-engine/actions/runs/30316220351) | FAIL - byte-identical to 0001, fix had no measurable effect |
| 0003 | guidance_scale 1.0 -> 6.0 fix | [30327666233](https://github.com/Y1X0/sallehly-ai-engine/actions/runs/30327666233) | FAIL - confirmed via SHA256 + direct visual inspection: byte-for-byte identical output to iteration 0001, despite +26% run duration. Fix had zero measurable effect; root cause still unknown. |
| 0004 | Metadata echo confirms guidance_scale=6.0 wiring is correct | [30331749263](https://github.com/Y1X0/sallehly-ai-engine/actions/runs/30331749263) | Diagnostic-only. Wiring confirmed correct via real diffusers source trace; root cause hypothesis narrowed to fp16 text-encoder overflow (T5-family models are well-documented to have this) - untested until iteration 0005 |
| 0005 | text_encoder fp32 upcast | [30333553288](https://github.com/Y1X0/sallehly-ai-engine/actions/runs/30333553288) | FAIL - 5th consecutive byte-identical output (127,355 bytes). text_encoder ruled out as the cause; only the transformer itself remains untested among fp16 submodules |
| 0006 | transformer fp32 upcast (last fp16 submodule) | [30336718604](https://github.com/Y1X0/sallehly-ai-engine/actions/runs/30336718604) | FAIL - 6th consecutive byte-identical output, no OOM. All fp16-precision hypotheses now exhausted. Added step_latent_norms diagnostic + configurable seed to test the denoising loop's real effect and input-sensitivity next |
| 0007 | seed 0 -> 42 | [30338955244](https://github.com/Y1X0/sallehly-ai-engine/actions/runs/30338955244) | CORRECTED - byte count/latent-norms genuinely changed (proving the pipeline is seed-sensitive), but direct visual inspection of the user-uploaded video disproved the "fixed" claim: still the same flat, textured, contentless output, just a different color cast. seed=0 was not uniquely degenerate - see 0008 |
| 0008 | Checkerboard artifact identified; disable VAE tiling | [30347507026](https://github.com/Y1X0/sallehly-ai-engine/actions/runs/30347507026) | OOM (13.45 GiB) - confirms tiling really was needed for memory at 17 frames, identical to the original iteration 0002 failure. See 0009. |
| 0009-0010 | Reduce frames to 9 instead of tiling | [30350022199](https://github.com/Y1X0/sallehly-ai-engine/actions/runs/30350022199) | HYPOTHESIS DISPROVEN - identical 13.45 GiB OOM at 9 frames as at 17 frames. The allocation does not scale with num_frames at all - likely resolution-dependent instead. |
| 0011 | Test resolution (480x272) as the OOM lever | [30352348205](https://github.com/Y1X0/sallehly-ai-engine/actions/runs/30352348205) | OOM avoided, but revealed something deeper: all 20 step_latent_norms are NaN from step 1 - a complete numerical failure, not just a checkerboard artifact. video.mp4 only 1,859 bytes. Model/scheduler mismatch ruled out by direct code audit (single from_pretrained call, no manual scheduler override). Testing tiling back ON at this same reduced resolution next to isolate the trigger. |
