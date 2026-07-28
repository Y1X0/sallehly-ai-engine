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
| 0003 | guidance_scale 1.0 -> 6.0 fix | [30327666233](https://github.com/Y1X0/sallehly-ai-engine/actions/runs/30327666233) | PENDING - real compute-time signal (+26% duration) suggests the fix activated, but pixel verification is blocked pending the video artifact (see report) |
