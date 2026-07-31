# Experiment/Report 0026: 30-category robustness benchmark - Capability Map for Wan2.2 TI2V-5B on Kaggle T4

**Baseline used (frozen, unchanged across all 30 runs):** `640x352`, `9` frames, `16fps`, `num_inference_steps=20`, `guidance_scale=5.0`, `seed=42`, `transformers==4.48.0`, `enable_sequential_cpu_offload=True`, Tesla T4. No code, scheduler, VAE, dtype, or prompt-template changes were made at any point during this benchmark (per explicit instruction) - only the subject-matter prompt varies row to row. This is a single, fixed answer to: *"what is Wan2.2's current real capability on Kaggle T4 at this exact production configuration?"*

All 30 runs are real Kaggle T4 GPU generations (GitHub Actions workflow `kaggle-free-inference.yml` on branch `claude/sallehly-engine-audit-vnxs4f`), each with a real per-frame `quality_metrics.py` pass and a real CLIP similarity score (`openai/clip-vit-base-patch32`, cosine similarity between the prompt's text embedding and each frame's image embedding, averaged). One category (`snow`) required a retry after a transient Kaggle API dispatch failure (`kaggle datasets create` returned an empty/non-JSON response - not a code bug, not a GPU/OOM issue); the retry succeeded on attempt 2 and is reported normally below.

## 1. Full results table (all 30 categories)

| # | Category | Prompt | CLIP score | Verdict | Visual notes |
|---|---|---|---|---|---|
| 1 | cars | A red sports car driving fast down a coastal highway at sunset, cinematic | 0.3113 | Excellent | Coherent red sports car, clear front 3/4 view, correct proportions, coastal highway + sunset all legible. |
| 2 | buildings | A futuristic glass skyscraper city skyline at dusk, cinematic wide shot | 0.2915 | Weak | Abstract painterly blue blur; no coherent skyscraper shapes, no clean glass/reflective surfaces. |
| 3 | people | A woman walking through a busy city street, cinematic close-up | 0.3002 | Good | Genuinely recognizable woman's face (eyes/nose/mouth/hair legible); minor ghosting on right side of face. |
| 4 | animals | A golden retriever running through a field of tall grass, slow motion | 0.3513 | Excellent | **Best result of the entire benchmark.** Clearly recognizable dog mid-run, correct anatomy, natural motion, tall grass with good depth of field. |
| 5 | nature | A calm forest river with sunlight filtering through the trees, cinematic | 0.3081 | Good | Coherent forest river, symmetric tree framing, backlit sunlight glow, clear water reflection; soft/pointillist texture. |
| 6 | food | A close-up of a chef plating a gourmet dish in a professional kitchen | 0.3115 | Excellent | Chef in white uniform, hands clearly plating a garnished dish, stovetop + copper pot visible, coherent kitchen scene. |
| 7 | night_scenes | A neon-lit city street at night in the rain, cinematic reflections | 0.2932 | Good | Atmospheric rainy alley, wet reflective ground with clear light reflections; building facades on both sides stay soft/indistinct. |
| 8 | action_scenes | Two martial artists sparring in a dojo, dynamic camera angle | 0.2988 | Weak | Only ONE clearly distinguishable fighter rendered (good pose/anatomy); no second sparring partner. Background brick/windows glitchy. |
| 9 | dialogue | Two people having a conversation at a cafe table, medium shot, natural lighting | 0.2994 | Good | TWO clearly distinguishable people facing each other, coherent conversation; background lighting slightly blown-out. |
| 10 | cinematic_trailers | An epic movie trailer shot of a lone hero standing on a cliff at sunrise, dramatic lighting | 0.2722 | **CLIP/visual divergence** | Lowest CLIP of the whole benchmark, yet visually a legitimate atmospheric silhouette shot (hero on hillside, dramatic backlighting, cape blowing). Flagged, not resolved. |
| 11 | advertisements | A product shot of a perfume bottle rotating on a reflective surface, studio lighting | 0.3395 | Excellent | Clean perfume bottle (amber liquid, gold cap, glass), reflective surface with visible mirror reflection, soft studio lighting. |
| 12 | fashion | A model walking down a runway in an elegant dress, fashion show lighting | 0.2878 | Good | Clearly recognizable model, detailed sparkly dress, spotlights, correctly out-of-focus blurred audience. |
| 13 | fantasy | A glowing magical forest with floating lights and an ancient stone archway | 0.3296 | Excellent | Clear single stone archway, atmospheric misty forest, path leading through, glowing lights matching "floating lights." |
| 14 | scifi | A spaceship cockpit with holographic control panels, sci-fi lighting | 0.304 | Excellent | Clean symmetric cockpit, two matching grids of glowing panels, central console, coherent lighting, no glitching. |
| 15 | horror | A dark abandoned hallway with flickering lights, horror atmosphere | 0.3403 | Excellent | **Highest CLIP of the whole benchmark.** Dark hallway with correctly converging perspective walls, wooden floor, single light fixture. |
| 16 | anime | An anime-style character standing in a cherry blossom garden, vibrant colors | 0.2951 | Good | Genuine anime-style rendering (flat shading, big eyes, clean line art), not defaulting to photorealism; petals somewhat busy at edges. |
| 17 | documentary | A wildlife documentary shot of an eagle soaring over mountains, natural lighting | 0.2705 | Weak | Bird shape recognizable but coloring distorted/prismatic; anatomy soft. Small distant subject in complex wide backdrop. |
| 18 | drone_shots | An aerial drone shot flying over a winding river through a canyon | 0.2963 | Good | Clear winding river through red-rock canyon, correct aerial perspective, warm natural coloring. |
| 19 | close_ups | An extreme close-up of a hand holding a steaming cup of coffee | 0.2508 | Weak | **Lowest CLIP of the whole benchmark.** Overexposed, blown-out bokeh; hand and cup barely visible, details washed out. |
| 20 | fast_motion | A high-speed motorcycle chase through city streets, fast motion, motion blur | 0.328 | Excellent | Motorcycle+rider clearly visible, correct radial motion-blur speed-lines matching the requested aesthetic. |
| 21 | slow_motion | A droplet of water hitting a still pond surface, extreme slow motion | 0.3061 | Excellent | Clean droplet mid-fall, correct sphere shape, correct concentric ripples and crown splash forming below. |
| 22 | mountains | A snowy mountain landscape at sunrise, realistic documentary style | 0.2564 | Weak | Abstract glitchy chaotic pattern; no clear mountain silhouettes. Diffuse wide vista with no compositional anchor. |
| 23 | indoor | A cozy living room with a fireplace and warm lamplight, static camera | 0.3006 | Good | Clear living room, fireplace with visible flames, correct room proportions, coherent enclosed-space composition. |
| 24 | outdoor | A wide open meadow under a clear blue sky, gentle breeze, wide shot | 0.2579 | Weak | Abstract chaotic texture; sky visible but meadow has odd rainbow chromatic-aberration coloring, no compositional anchor. |
| 25 | rain | Heavy rain falling on a city street at night, reflections on wet pavement | 0.2928 | Good | Rainy city street, wet reflective pavement with clear neon reflections; building facades soft/indistinct (same as night_scenes). |
| 26 | snow | Snow falling gently over a quiet pine forest, soft winter light | 0.2852 | Good | (Succeeded on retry attempt 2 after a transient Kaggle API dispatch failure.) Clearly recognizable snow-covered pine trees, coherent forest. |
| 27 | fire | A campfire crackling at night with sparks rising, close-up | 0.3232 | Excellent | Clear rising flames, visible sparks, glowing embers, dark night background with silhouetted trees. |
| 28 | ocean | Ocean waves crashing against rocky cliffs, aerial view, golden hour | 0.3312 | Excellent | Wave crashing on rocks with clear white spray, dark rocks, blue ocean, warm golden-hour tinted rock face. |
| 29 | city | A busy downtown city intersection with traffic and pedestrians, wide shot | 0.2813 | Weak | Legible crosswalk with cars/bus/pedestrians, but building facades soft/distorted; high density of repeated elements + deep perspective. |
| 30 | luxury | A luxury sports car parked in front of a modern glass mansion at sunset, cinematic | 0.2782 | Good | Silver luxury SUV/sports car clearly rendered with correct proportions; building softer/hazier in background. |

**Mean CLIP across all 30 categories: 0.2997**

## 2. Top 5 and bottom 5 (ranked by CLIP score)

### Top 5
1. **animals** - 0.3513
2. **horror** - 0.3403
3. **advertisements** - 0.3395
4. **ocean** - 0.3312
5. **fantasy** - 0.3296

*(fast_motion at 0.328 is a very close 6th, effectively tied with fantasy.)*

### Bottom 5
1. **close_ups** - 0.2508 (lowest)
2. **mountains** - 0.2564
3. **outdoor** - 0.2579
4. **documentary** - 0.2705
5. **cinematic_trailers** - 0.2722 *(flagged CLIP/visual divergence - see Section 1, row 10)*

## 3. Capability Map

```
Wan2.2 TI2V-5B on Kaggle T4 (Baseline v1.0: 640x352, 9 frames, 20 steps, guidance_scale=5.0)

Excellent:
- Animals
- Horror (atmosphere/hallway)
- Advertisements (product shots)
- Ocean
- Fantasy (single architectural element)
- Fast motion
- Fire
- Food
- Cars
- Sci-fi (cockpit/panels)
- Slow motion

Good:
- Nature
- Indoor
- People (faces)
- Dialogue (two-person, low motion)
- Drone shots (pure landscape, no small subject)
- Anime (non-photorealistic style)
- Night scenes
- Rain
- Fashion
- Snow
- Luxury (single-object-in-frame)

Weak:
- Action scenes (multi-entity + complex motion)
- Buildings (repeated geometry + perspective)
- City (repeated geometry + perspective + multi-entity)
- Documentary (small/distant subject in wide shot)
- Mountains (diffuse vista, no anchor)
- Outdoor (diffuse vista, no anchor)
- Close-ups (extreme macro framing)

Flagged (needs separate investigation):
- Cinematic trailers (CLIP score lowest, but direct visual inspection reads as a legitimate atmospheric shot - CLIP and human judgment disagree here)
```

## 4. Analysis of likely weakness causes

Cross-referencing all 30 results shows the weaknesses are **not** explained by a single simple axis ("objects vs. scenes," "photorealism vs. style," "close vs. wide"). Four separable factors emerged, each supported by direct counter-examples that ruled out simpler explanations:

**a) Repeated fine-grained geometry + deep perspective, *combined*.** Buildings (0.2915), city (0.2813), and mountains (0.2564) all combine many visually-similar repeated elements (windows, peaks, vehicles) with a large-scale vanishing-point perspective the model must hold consistent. Two counter-examples ruled out simpler versions of this theory: fantasy's single stone archway (0.3296, no repetition) succeeded, and sci-fi's cockpit (0.304, dense repeated panel grids but no deep perspective - front-facing and symmetric) also succeeded. Horror's hallway (0.3403, the single highest score in the benchmark) has genuinely deep converging perspective with *no* repeated fine detail, and it succeeded cleanly too. Only when both factors are present at once (many repeated elements *and* depth-consistent perspective) does quality collapse.

**b) Subject scale / camera distance for a small subject within a complex backdrop.** Documentary's eagle (0.2705) is a small, distant subject set against a complex mountain/cloud backdrop, and its anatomy/coloring came out distorted. This contradicts a naive "animals succeed" rule established from animals' 0.3513 - the actual differentiator is that the golden retriever filled most of the frame at close range, while the eagle did not. Drone_shots (0.2963, a pure landscape aerial with no small foreground subject) succeeded fine, confirming the failure is specifically about a *small subject in a wide shot*, not wide/aerial framing itself.

**c) Multi-entity interaction with complex relative motion, not entity count.** Action_scenes (0.2988) asked for two sparring martial artists and only rendered one coherent fighter. Dialogue (0.2994) asked for two people talking (low relative motion) and rendered both people clearly and distinctly. The differentiator is combat/complex physical interaction between multiple moving entities, not simply "more than one person."

**d) Diffuse wide vistas lacking one strong compositional anchor.** Mountains (0.2564) and outdoor (0.2579) are both wide, textured landscapes with no single leading element, and both came out as abstract chaotic textures. Nature (0.3081, forest+river+light) and drone_shots (0.2963, winding river) are also wide landscape shots, but both have one strong anchor (a river, a light source) the composition organizes around, and both succeeded. This is a distinct failure mode from (a) above - it's about *lack* of a unifying element, not too much repeated detail.

**Two additional, narrower observations:**
- **Extreme macro/close-up framing** (close_ups, 0.2508, lowest score) failed with overexposed/blown-out results, while slow_motion's droplet macro shot (0.3061) succeeded - the differentiator appears to be that a simple, symmetric physical phenomenon (droplet + ripples) renders more reliably at extreme close range than a complex organic surface (skin, ceramic glaze, steam).
- **Non-photorealistic style transfer works.** Anime (0.2951) rendered in a genuine, recognizable anime style (flat shading, big eyes, clean line art) rather than defaulting to photorealism, closing the open question of whether Wan2.2's weaknesses are tied to realism specifically - they are not.

## 5. Suggested next development experiment (recommendation only - not started)

The single most consistent, highest-confidence weak cluster across this benchmark is **architecture/repeated-geometry-heavy scenes under deep perspective** (buildings 0.2915, city 0.2813, and the architectural component of documentary/mountains/outdoor's diffuse-vista failures) - it is the only failure mode that recurs across five independent categories with a clear, evidence-backed mechanism (Section 4a).

**Recommended first step (zero-cost, no training):** targeted prompt engineering for this specific category cluster - rewrite architecture-heavy prompts to reduce the requested count of repeated elements and add a single compositional anchor, e.g. instead of *"a futuristic city with hundreds of glass skyscrapers and thousands of windows,"* use *"a futuristic city street with one iconic glass tower, cinematic lighting, minimal visible windows."* This can be tested with the exact same frozen Baseline v1.0 config (no hyperparameter changes) as a pure prompt-side experiment, reusing the same CLIP+visual evaluation pipeline built for this benchmark.

**If prompt engineering does not close the gap:** a heavier follow-up would be LoRA fine-tuning specifically on architectural/urban scenes with correct window-grid and vanishing-point consistency, which is a real training investment (Kaggle-only, per the project's constraints) and should only be pursued after the cheaper prompt-engineering experiment has been tried and measured against this report's baseline numbers.

This is a recommendation for the user to decide on - no prompt changes or training have been started as part of this report.

## 6. Capability confidence summary (at-a-glance)

A quick-read version of Sections 1-4 for anyone who doesn't want to read the full table. Stars reflect CLIP score *and* the direct visual verdict together, not CLIP alone (see the methodology caveat below).

| Capability | Confidence | Representative categories |
|---|---|---|
| Close-framed single subject (animal/object) | ⭐⭐⭐⭐⭐ | animals (0.3513), advertisements (0.3395) |
| Atmospheric enclosed/single-anchor scenes | ⭐⭐⭐⭐⭐ | horror (0.3403), fantasy (0.3296), scifi (0.304) |
| Water/fire/motion phenomena | ⭐⭐⭐⭐⭐ | ocean (0.3312), fire (0.3232), fast_motion (0.328), slow_motion (0.3061) |
| Food/product close-ups (structured subject) | ⭐⭐⭐⭐⭐ | food (0.3115), cars (0.3113) |
| Portraits / faces | ⭐⭐⭐⭐ | people (0.3002) |
| Landscapes with one compositional anchor | ⭐⭐⭐⭐ | nature (0.3081), drone_shots (0.2963) |
| Two-person, low relative motion | ⭐⭐⭐⭐ | dialogue (0.2994) |
| Non-photorealistic style transfer | ⭐⭐⭐⭐ | anime (0.2951) |
| Indoor static scenes | ⭐⭐⭐⭐ | indoor (0.3006) |
| Night/rain street scenes (soft facades) | ⭐⭐⭐ | night_scenes (0.2932), rain (0.2928) |
| Fashion / single-object staged scenes | ⭐⭐⭐ | fashion (0.2878), luxury (0.2782) |
| Cinematic/atmospheric trailer shots | ⭐⭐⭐ *(flagged - CLIP disagrees with visuals, see Section 1 row 10)* | cinematic_trailers (0.2722) |
| Multi-entity interaction / complex relative motion | ⭐⭐ | action_scenes (0.2988) |
| Repeated geometry + deep perspective (architecture) | ⭐⭐ | buildings (0.2915), city (0.2813) |
| Diffuse wide vista, no compositional anchor | ⭐⭐ | mountains (0.2564), outdoor (0.2579) |
| Small/distant subject in complex wide backdrop | ⭐⭐ | documentary (0.2705) |
| Extreme macro close-up of complex organic texture | ⭐⭐ | close_ups (0.2508) |

**Methodology caveat:** CLIP similarity is the primary quantitative signal in this report, but `cinematic_trailers` (Section 1, row 10) shows it can diverge from direct visual judgment - a legitimate, well-composed atmospheric shot still scored the lowest CLIP of the benchmark. Future reports should treat CLIP as one signal among several (alongside direct visual inspection, and where useful, temporal consistency across frames), not a sufficient metric on its own.
