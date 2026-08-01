# Experiment/Report 0027: Phase 2 - Architecture Prompt Study (Case A vs Case B)

**Context.** Report 0026 (30-category robustness benchmark) identified "repeated fine-grained geometry + deep perspective, combined" as Wan2.2 TI2V-5B's most consistent weak cluster (buildings 0.2915, city 0.2813 CLIP, both well below the 0.2997 benchmark mean). Before committing to any fine-tuning, this experiment tests a single question, agreed with the user in advance: **is the architecture weakness caused by how the prompt is written, or is it a real ceiling on the model's current capability?**

**Baseline used (frozen, unchanged across all 17 runs):** `640x352`, `9` frames, `16fps`, `num_inference_steps=20`, `guidance_scale=5.0`, `seed=42`, `transformers==4.48.0`, `enable_sequential_cpu_offload=True`, Tesla T4 - identical to eval/reports/0026's Baseline v1.0. No hyperparameter, scheduler, VAE, or dtype was touched at any point; only the prompt varied.

**Methodology (agreed with the user before any run was dispatched).** 17 real Kaggle T4 runs in a fixed sequence: a **Control prompt** ("A red sports car driving through a neon-lit city at night, cinematic") repeated 4 times, interleaved before each of 4 hypothesis groups of 3-4 architecture prompts each:

- **Group A - reduce repetition**: describe a single, concrete architectural subject (isolated skyscraper / single office tower / lone modern building).
- **Group B - reduce detail via abstract style language**: ask for less complexity using style words (glass + minimal windows / concrete + smooth facade / minimalist + clean lines).
- **Group C - add a compositional anchor**: place a clear foreground subject in front of the building (car / person / fountain).
- **Group D - change camera angle**: street level / aerial / oblique / extreme close-up, same building description each time.

**Exit criteria (locked in advance, before any result was seen):**
- **Case A (prompting issue):** any group shows a CLIP increase **and** a clear visual improvement over the buildings/city baseline, **and** the Control stays stable across all 4 measurements → no LoRA; produce an Architecture Prompt Guide instead.
- **Case B (model capability ceiling):** all 4 groups fail to improve, Control stable → begin LoRA design.
- A drifting Control would invalidate the round's comparability and had to be flagged, not silently averaged over.

All 17 runs are real Kaggle T4 GPU generations, each with a real `eval/quality_metrics.py` pass (CLIP via `openai/clip-vit-base-patch32`, sharpness, saturation, frame-delta) and a real decoded-frame thumbnail visually inspected before scoring - no result in this report was guessed from metrics alone.

## 1. Full results table (all 17 steps)

| # | Step | Prompt | CLIP | Visual verdict |
|---|---|---|---|---|
| 1 | Control-1 | A red sports car driving through a neon-lit city at night, cinematic | 0.3474 | Excellent - clean recognizable red sports car, correct proportions, neon-lit city backdrop with clear reflections. |
| 2 | A.1 | An isolated skyscraper standing against a clear sky, cinematic wide shot | 0.3156 | Good - single clean tapered skyscraper silhouette, sharp edges, no repeated-window chaos. |
| 3 | A.2 | A single office tower at dusk, cinematic wide shot | 0.301 | Mixed - one distinguishable tower, but background filled with a busy repeated skyline of small lit buildings. |
| 4 | A.3 | A lone modern building at sunset, cinematic wide shot | 0.317 | Excellent - single building silhouette clean against a smooth sunset gradient, zero repeated elements. |
| 5 | Control-2 | (same as Control-1) | 0.3474 | Byte-identical to Control-1 (109532-byte video, same every metric). |
| 6 | B.1 | A glass office building with minimal windows, cinematic wide shot | 0.3064 | Good - clean glass facade, regular window grid but not chaotic; frontal/flat composition, no deep perspective. |
| 7 | B.2 | A concrete office building with a smooth facade, cinematic wide shot | 0.2775 | Weak - first Group A/B result below the buildings baseline; visible geometric distortion at panel edges. |
| 8 | B.3 | A minimalist office building facade, clean lines, cinematic wide shot | 0.2424 | Very weak - new lowest CLIP of the entire project (below Phase 1's close_ups at 0.2508); blocky, tiled, glitchy mosaic, no coherent building. |
| 9 | Control-3 | (same as Control-1) | 0.3474 | Byte-identical to Control-1/2. |
| 10 | C.1 | A red sports car parked in front of a glass skyscraper, cinematic wide shot | 0.2718 | Notable failure mode - the car renders perfectly, but the skyscraper behind it dissolves into soft out-of-focus bokeh blur. |
| 11 | C.2 | A person standing before a glass tower, cinematic wide shot | 0.3129 | Good - person AND tower both clearly rendered; anchor and building share the same depth of field. |
| 12 | C.3 | A stone fountain in front of a city hall building, cinematic wide shot | 0.3148 | Excellent - fountain beautifully rendered, city hall behind it also legible (facade, windows visible). |
| 13 | Control-4 | (same as Control-1) | 0.3474 | Byte-identical to Control-1/2/3 - 4/4 perfect stability across the whole study. |
| 14 | D.1 | A modern glass skyscraper, street level view looking up, cinematic | 0.2723 | Weak - requested camera angle not followed (rendered elevated/aerial-ish instead); dense repeated skyline reappears in the background. |
| 15 | D.2 | A modern glass skyscraper, aerial view, cinematic | 0.3331 | Good - single clean cylindrical tower, background is distant textured forest/ground, not competing nearby architecture. |
| 16 | D.3 | A modern glass skyscraper, oblique angle view, cinematic | 0.2938 | Borderline - correctly converging oblique perspective, but texture reads as painterly/abstract rather than coherent. |
| 17 | D.4 | A modern glass skyscraper facade, extreme close-up, cinematic | 0.3053 | Good - two glass facade planes meeting at a corner, clean regular window-grid texture, highest sharpness of the study (10.05). |

**Group averages:** A = 0.3112 (n=3) | B = 0.2754 (n=3) | C = 0.2998 (n=3) | D = 0.3011 (n=4) | all 13 non-Control runs = 0.2972, vs. buildings (0.2915) / city (0.2813) from report 0026.

## 2. Control stability

All 4 Control measurements (steps 1, 5, 9, 13) returned **exactly CLIP = 0.3474**, with byte-identical 109,532-byte videos and identical sharpness/saturation/frame-delta values every time. This is a fully deterministic, zero-drift result (same seed=42, same prompt, same everything) - it confirms every comparison across this 17-run round is made against a stable reference, so differences between groups reflect the architecture prompts themselves, not environment or generation-run variance.

## 3. Per-group analysis

**Group A - describe a single, concrete subject: 3/3 succeeded.** All three prompts (isolated skyscraper, single office tower, lone modern building) beat both buildings (0.2915) and city (0.2813). A.1 and A.3 were visually clean with zero repeated elements; A.2 was the weakest of the three because "wide shot" framing let a busy repeated skyline back into the background even with a singular named subject. This is the strongest, most consistent group in the study.

**Group B - describe an abstract style/detail-reduction goal: 1/3 succeeded, net negative.** B.1 ("minimal windows") worked because the facade stayed frontal and flat with no deep perspective. B.2 ("smooth facade") and B.3 ("minimalist, clean lines") both underperformed the buildings baseline, with B.3 producing the single lowest CLIP score of the entire project (0.2424, worse than Phase 1's close_ups). This is the key counter-evidence in the study: **wording that targets an abstract style goal is not a reliable strategy**, even though it sounds like it should reduce complexity in the same way Group A's concrete-subject wording did.

**Group C - add a compositional anchor: 2/3 succeeded.** C.1 (car parked in front of a skyscraper) failed because the car rendered perfectly while the building behind it dissolved into soft bokeh blur - the model solved the "easy" foreground subject and avoided the "hard" architecture rendering rather than fixing it. C.2 (a person looking up at the tower) and C.3 (a fountain in front of city hall) both succeeded because the anchor and the building occupied a similar depth of field, keeping both legible. The deciding factor is not "does the prompt have an anchor" but **whether the composition's implied depth of field keeps the building in focus**.

**Group D - change camera angle: mixed, 2 clearly good, 1 weak, 1 borderline.** D.1 ("street level looking up") failed (0.2723) because the model didn't actually follow the requested angle and instead reintroduced a dense repeated skyline behind the tower. D.2 ("aerial view", 0.3331) was the second-best non-Control result of the entire study - the elevated framing put clean distance between the tower and any competing nearby architecture. D.3 ("oblique angle") was borderline/painterly. D.4 ("extreme close-up") succeeded (0.3053, highest sharpness of the study) because at extreme close range the repeated window grid becomes a simple, symmetric texture pattern rather than a large structure the model has to hold coherent - consistent with Phase 1's finding that close-ups succeed for simple/symmetric subjects and fail for complex organic ones.

## 4. Final decision

**Case A: the architecture weakness is a prompting issue, not a hard ceiling on Wan2.2 TI2V-5B's current capability at Baseline v1.0.**

The evidence for Case A is strong and consistent:
- Group A: 3/3 clean wins over both buildings and city.
- Group C: 2/3 wins, with a clear, reproducible mechanism explaining the one failure (depth-of-field/anchor placement, not architecture itself).
- Group D: the aerial angle (D.2) and extreme close-up (D.4) both beat baseline clearly, each with a specific, explainable reason (distance from competing architecture; grid-as-texture at close range).
- Control stayed perfectly stable across all 4 measurements, so every comparison above is trustworthy.

This is **not** a case of "any prompt tweak helps" - Group B (1/3, and the single worst result of the entire project in B.3) and D.1 (camera-angle instruction not followed) are real counter-examples that rule out a naive reading. The pattern that separates success from failure is specific: **wording that names a single, concrete architectural subject succeeds; wording that asks for an abstract stylistic outcome does not; compositions must keep the building in the same depth of field as any foreground anchor; and camera angles that create visual distance from competing repeated architecture (aerial, extreme close-up) outperform angles that reintroduce a dense skyline (street level).**

## 5. Recommendation: Architecture Prompt Guide (no LoRA, no fine-tuning)

Based on Case A, the recommended next step is a lightweight, zero-training addition to the prompt-writing guidance for architecture/urban scenes, built directly from this study's own before/after evidence:

**Principle 1 - Name one concrete subject, not an abstract style goal.**
- Before (Phase 1 baseline): *"A futuristic glass skyscraper city skyline at dusk, cinematic wide shot"* → 0.2915, abstract painterly blur.
- Before (this study, failed): *"A minimalist office building facade, clean lines, cinematic wide shot"* → 0.2424, worst result of the project.
- After (this study, succeeded): *"An isolated skyscraper standing against a clear sky, cinematic wide shot"* → 0.3156, clean single tower.
- Rule: use "isolated / single / lone + [specific building type]" rather than "minimalist / smooth / clean-lines + [building]".

**Principle 2 - If adding a foreground anchor, keep it in the same depth of field as the building.**
- Before (failed): *"A red sports car parked in front of a glass skyscraper"* → 0.2718, car sharp, tower dissolves into bokeh blur.
- After (succeeded): *"A person standing before a glass tower"* / *"A stone fountain in front of a city hall building"* → 0.3129 / 0.3148, anchor and building both legible.
- Rule: prefer anchors and phrasing that imply the subject is looking at or standing near the building (shared plane), not a close macro foreground object that would naturally throw the background out of focus.

**Principle 3 - Prefer camera angles that separate the building from competing repeated architecture.**
- Before (failed): *"street level view looking up"* → 0.2723, model reintroduced a dense nearby skyline.
- After (succeeded): *"aerial view"* → 0.3331; *"extreme close-up"* on a single facade → 0.3053.
- Rule: for a single building as the subject, aerial framing or an extreme close-up on one facade are safer defaults than street-level framing, which tends to pull a full urban backdrop back into frame.

This guide can be adopted immediately at zero cost (prompt-side only, same frozen Baseline v1.0 config) and validated further with ordinary production prompts as they come in. No LoRA or fine-tuning work is recommended at this time - that remains the fallback only if future architecture prompts, written per this guide, still underperform.
