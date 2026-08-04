# Dataset v1.0 (Pilot) - Specification

Status: **spec only, zero clips downloaded, zero rights cleared.** This
document is the "constitution" for the first real training dataset -
written before any sourcing starts, per explicit project decision. Its
job is to make the pilot dataset's design defensible and auditable, not
to describe work already done.

## 0. Purpose (what this dataset is for, and what it is not for)

This pilot dataset exists to answer exactly one question: **can this
model's weights actually be improved by training, at all?** It is not
meant to produce a polished, general-purpose fine-tune. Success is a
measurable, honest improvement on the specific failure cases this
project already diagnosed with real evidence - not a high aggregate
CLIP score, not broad category coverage.

Every category below traces to a specific finding in
`docs/KNOWN_LIMITATIONS.md` and its underlying report. Nothing here is
speculative "might help" data - if a category doesn't map to a
documented weakness or a documented strength worth protecting, it isn't
in this dataset.

## 1. Design principles

1. **Quality over quantity.** 150 excellent buildings clips beats 5,000
   average ones. Every clip must individually clear the quality bar in
   Section 4 - no bulk-download-then-filter-later.
2. **Targeted, not random.** Every category exists because it maps to a
   real diagnosed weakness (or, for one category, a real strength worth
   protecting from regression). No "diverse for diversity's sake" filler.
3. **One source for the pilot.** Pexels only (Section 5) - reduces the
   number of simultaneous unknowns (license terms, quality baseline,
   metadata conventions) to one, so if the pilot LoRA underperforms, the
   cause is easier to isolate. Academic multi-source datasets
   (WebVid/HD-VILA/Panda-70M/etc.) are explicitly deferred to Phase 2/3
   scale-up (Section 7), not used here.
4. **Small first, scale only on evidence.** This spec covers Phase 1
   (pilot) only. Phase 2 (5k-10k) and Phase 3 (50k-100k) are gated on
   the pilot LoRA showing a real, visually-confirmed improvement on the
   target failure cases - not scheduled in advance.

## 2. Training-config constraints this dataset must satisfy

Taken directly from `services/training/configs/wan22_finetune.yaml`
(the real, already-committed Stage A LoRA config) - not invented here:

| Constraint | Value | Why it matters for sourcing |
|---|---|---|
| Training resolution | `960x544` | Source clips should be **at least** 1280x720 so downsampling, not upsampling, is what happens. Upsampled source footage would train the model on soft, low-detail data. |
| `fps` | 16 | Source fps should be a clean multiple/match (24/25/30 fps source is fine, ffmpeg resamples cleanly to 16). |
| `max_frames` | 81 | At 16fps this is ~5.06s. **Every clip must be at least ~6s long** to leave trimming margin - a 5.06s-exact clip gives the pipeline no room to cut a clean, non-boundary segment. |
| LoRA rank/alpha | 16 / 32 | Not a sourcing constraint, noted for context - this is a small-capacity adapter, consistent with a small, targeted dataset rather than a broad one. |

## 3. Tagging taxonomy (maps directly onto `ClipRecord.tags`)

`services/training/src/training/dataset/records.py`'s `ClipRecord`
already has a `tags: list[str]` field - this taxonomy is designed to be
written straight into that field during ingestion, so category counts
are a real, auditable query against the manifest, not a claim in a
spreadsheet. Every clip gets exactly one **category tag** (below) plus
0+ **attribute tags** from that category's list.

## 4. Category breakdown (pilot target: 800 clips)

Minimum quality bar for **every** clip, all categories: source
resolution >=1280x720, duration >=6s, single continuous shot (no hard
cuts mid-clip - the VAE/temporal path assumes continuous motion), no
visible watermark/logo burn-in, no heavy compression artifacts, mp4/h264
container preferred.

### A. `multi_entity_interaction` - 200 clips (highest priority)

**Why:** Phase 4 Test A (`eval/reports/0030`) found a real, seed-independent
ceiling - a 3-person combat prompt rendered exactly 2 clear entities
across all 3 tested seeds, never 3. This is the single most decisive
"prompting can't fix this" finding of the whole project.

**Attribute tags:** `entity_count_3`, `entity_count_4plus`, `combat`,
`dance`, `team_sport`, `coordinated_crowd`, `camera_close`, `camera_wide`,
`day`, `night`.

**Composition target:** at least 120 of the 200 clips must show 3+
clearly distinguishable people in simultaneous active interaction
(not just present in frame - actually interacting) - this is the exact
gap being targeted, so it cannot be the minority of the category.

**Captioning:** hand-written or hand-verified, not left to the heuristic
captioner alone. Every caption must explicitly state the real entity
count in words ("three dancers," "four players") - the training signal
this category exists for is the word-to-count mapping itself.

### B. `distant_small_subject` - 200 clips (highest priority)

**Why:** Phase 4 Test C found the model never honored a "distant"/"small
subject" framing instruction across 3 seeds - the subject rendered
large/foreground every time regardless of wording. Also documented in
`docs/KNOWN_LIMITATIONS.md` as a hard ceiling.

**Attribute tags:** `subject_human`, `subject_animal`, `distance_far`,
`distance_mid`, `backdrop_mountain`, `backdrop_plain`, `backdrop_urban`,
`day`, `dusk`.

**Composition target:** at least 140 of the 200 clips must have the
main subject occupy a clearly small fraction of the frame (a rough
guide: subject height under ~15% of frame height) against a wide
backdrop - matching the exact "wolf in a distant valley" case that failed.

**Captioning:** hand-verified. Every caption must contain explicit
distance language ("in the distance," "far away," "a small figure
against...") - same reasoning as category A, the word-to-spatial-scale
mapping is the point.

### C. `dense_architecture` - 150 clips

**Why:** Phase 1 (`eval/reports/0026`) found buildings (0.2915) and
city (0.2813) among the weakest categories; Phase 4 Test B
(`eval/reports/0030`) found dense architecture is only *mostly* stable
(1 of 3 seeds degraded to blocky, repeated-facade texture). Prompting
(Phase 2/3B) fixed a lot of this already - this category exists to lock
the remaining instability into the weights, not to teach the model
architecture from zero.

**Attribute tags:** `skyscraper`, `glass_facade`, `aerial_angle`,
`street_angle`, `oblique_angle`, `day`, `night`, `rain`,
`single_building`, `skyline_multiple`.

**Composition target:** matches the user's own worked example - a mix
across angle (aerial/street/oblique), time of day, and weather, rather
than 150 near-identical daytime skyscraper shots. Bias toward aerial
and single-building framing (Phase 2's Group D found these most
reliable) but keep enough street-level/skyline examples that the model
sees the harder cases too, not only the easy ones.

### D. `wide_anchor_camera` - 100 clips

**Why:** Phase 1 found diffuse wide vistas with no compositional anchor
weak (mountains 0.2564, outdoor 0.2579) while anchored wide shots
succeeded (nature 0.3081, drone_shots 0.2963); Phase 2 found aerial
framing consistently outperforms street-level. This category reinforces
the "wide scene needs one anchor" rule directly into the weights and
adds camera-angle diversity.

**Attribute tags:** `drone_aerial`, `landscape_single_anchor`,
`river_anchor`, `light_source_anchor`, `tracking_shot`.

**Composition target:** every clip must have one unambiguous
compositional anchor (a river, a single structure, a light source) -
diffuse, anchor-less wide shots are exactly what this category should
*not* contain, since the goal is reinforcing the anchored pattern.

### E. `animals_regression_guard` - 150 clips

**Why:** animals scored highest of the entire Phase 1 benchmark (0.3513).
This category is not fixing a weakness - it exists to give
`Wan22EvaluationHook`'s `RegressionDetector`
(`services/training/src/training/wan22/evaluation_hooks.py`) a real
signal that fine-tuning on the four weak categories above didn't quietly
degrade a category the model already handles well.

**Attribute tags:** `close_framed`, `wide_framed`, `single_animal`,
`in_motion`, `static_pose`.

**Composition target:** representative of what already works, not
adversarial - the point is a stable, high-quality baseline the
regression check can compare against after every checkpoint.

### Total: 800 clips (200+200+150+100+150) - inside the 500-1,000 pilot range

## 5. Source (pilot: single source only)

**Pexels**, for the reasons in Section 1.3: license terms allow broad
reuse and the catalog quality/diversity is strong, and using one source
keeps the pilot's variables down to one.

**Open item, blocking, not yet done:** Pexels' current license terms
must be checked specifically for AI/ML **training** use - not just
general reuse - before a single clip is downloaded. Stock-video
licenses have been changing fast on this exact point industry-wide, so
"Pexels is generally free to use" is not sufficient; the license page
must be read fresh, dated, and the relevant clause quoted into this
document (Section 6) before `rights_cleared=True` is set on any clip.
This has **not** been done yet - it is the actual next task, not a
formality to skip.

## 6. License verification log

*(Empty until Section 5's review happens. Every entry here must cite
the specific license page/date/clause checked - not a general
impression of the platform's reputation.)*

| Date checked | Source | Clause found (verbatim or close paraphrase) | Verdict |
|---|---|---|---|
| *(pending)* | Pexels | *(pending)* | *(pending)* |

## 7. Captioning approach

`training.dataset.captions.HeuristicCaptionProvider` (real, already
built) can produce a first-pass caption for every clip. For categories
A and B specifically (Section 4), heuristic captions are **not
sufficient on their own** - the training signal those two categories
exist to provide depends on precise count/distance language that a
generic heuristic captioner is unlikely to reliably produce. Plan:
heuristic pass first for all 800 clips, then a hand-verification pass
focused on categories A and B (400 clips) to confirm/correct the
count/distance language before `ingest_dataset.py` runs. Categories
C/D/E can rely on the heuristic pass alone for the pilot.

## 8. Explicit non-goals for v1.0

- Not attempting full category coverage of the original 30-category
  benchmark - only the categories tied to a real diagnosed weakness (or
  the one regression-guard category).
- Not mixing sources yet (Section 1.3).
- Not targeting 5k-10k+ scale yet (Section 7 below).
- Not writing final captions by hand for all 800 clips - only the two
  categories where precision matters most for the training signal.

## 9. Phase gate to scale beyond this pilot

Move to Phase 2 (5k-10k, `wan22_finetune.yaml`'s full `max_train_steps:
1500` run) **only if** the pilot LoRA (a short run, ~50-100 steps per
`docs/EXECUTION_PLAN_FIRST_GPU_RUN.md` Section 5 step 5) shows a real,
visually-confirmed improvement - not just a CLIP delta - on at least
one of categories A or B's exact failure cases (a 3-entity prompt
rendering a real 3rd entity; a "distant" prompt actually rendering the
subject smaller/farther), checked via `Wan22EvaluationHook` +
`RegressionDetector` against the untrained baseline. If the pilot LoRA
shows no real change on these cases, the next step is diagnosing why
(dataset size, caption precision, LoRA rank, training steps) before
scaling the dataset further - scaling a dataset that isn't working
larger is not the fix by default.
