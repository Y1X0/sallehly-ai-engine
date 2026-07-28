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
| 0007 | seed 0 -> 42 (root cause found) | [30338955244](https://github.com/Y1X0/sallehly-ai-engine/actions/runs/30338955244) | LIKELY FIXED, pending pixel confirmation - video.mp4 finally differs (276,938 bytes vs the identical 127,355 across all 6 prior iterations), step_latent_norms shows real 55.9% convergence. seed=0 was the actual degenerate input all along, not model precision. |
