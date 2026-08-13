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

1. **Quality over quantity.** 100 excellent buildings clips beats 5,000
   average ones. Every clip must individually clear the quality bar in
   Section 4 - no bulk-download-then-filter-later.
2. **Targeted, not random.** Every category exists because it maps to a
   real diagnosed weakness (or, for one category, a real strength worth
   protecting from regression). No "diverse for diversity's sake" filler.
3. **Free, openly-licensed sources only - no paid stock, no general
   "royalty-free" stock sites.** Section 5/6 rejected Pexels and Pixabay
   (both explicitly ban ML training use) and deliberately does not
   pursue a paid AI-training-licensed marketplace (Wirestock etc.) -
   this project is improving an existing model, not building a
   commercial data-licensing relationship. The real sources are
   openly-licensed collections: Wikimedia Commons, NASA's public-domain
   media, curated public-domain/CC subcollections of the Internet
   Archive, and individually CC-licensed Vimeo uploads (Section 5/6).
4. **Small first, scale only on evidence.** This spec covers the first
   proof stage and Dataset v1 (Section 4) only. Phase 2 (5k-10k) and
   Phase 3 (50k-100k) are gated on real, visually-confirmed improvement
   on the target failure cases - not scheduled in advance (Section 9).

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

## 4. Category breakdown (Dataset v1 target: 600 clips)

Minimum quality bar for **every** clip, all categories: source
resolution >=1280x720, **6s <= duration <= 120s** (upper bound is
`DatasetValidator`'s real, enforced `max_duration_sec` default - found
the hard way in the first live Stage 0 ingest run, where 6 of 9
sourced clips were rejected for exceeding it), single continuous shot
(no hard cuts mid-clip - the VAE/temporal path assumes continuous
motion; long, multi-scene compilations like a 34-minute highlights
reel are exactly what this ceiling catches, even when individually
they'd otherwise look like good candidates), no visible watermark/logo
burn-in, no heavy compression artifacts, mp4/h264 container preferred.

### A. `multi_entity_interaction` - 150 clips (highest priority)

**Why:** Phase 4 Test A (`eval/reports/0030`) found a real, seed-independent
ceiling - a 3-person combat prompt rendered exactly 2 clear entities
across all 3 tested seeds, never 3. This is the single most decisive
"prompting can't fix this" finding of the whole project.

**Attribute tags:** `entity_count_3`, `entity_count_4plus`, `combat`,
`dance`, `team_sport`, `coordinated_crowd`, `camera_close`, `camera_wide`,
`day`, `night`.

**Composition target:** at least 90 of the 150 clips must show 3+
clearly distinguishable people in simultaneous active interaction
(not just present in frame - actually interacting) - this is the exact
gap being targeted, so it cannot be the minority of the category.

**Captioning:** hand-written or hand-verified, not left to the heuristic
captioner alone. Every caption must explicitly state the real entity
count in words ("three dancers," "four players") - the training signal
this category exists for is the word-to-count mapping itself.

### B. `distant_small_subject` v1.1 - 150-200 clips (highest priority)

**Why (revised, broader root cause - not just the one example that
found it):** Phase 4 Test C found the model never honored a
"distant"/"small subject" framing instruction across 3 seeds. The
original v1.0 category was scoped too narrowly around that one example
("a wolf in a distant valley"). The real underlying weakness is
broader: **the model does not reliably respect subject-scale/framing
in wide scenes** - the same root cause also explains Phase 1's
`documentary` (eagle, weak), `outdoor`/`mountains` (weak, diffuse wide
vistas), and parts of the drone-shot weaknesses. Redefining the
category around the root cause, not the one triggering example, means
this dataset addresses the actual failure mode instead of a single
instance of it. Also documented in `docs/KNOWN_LIMITATIONS.md` as a
hard ceiling.

**Definition:** a wide shot containing a clearly identifiable subject
occupying a small portion of the frame. Subject type is intentionally
open - not restricted to animals, and not restricted to the exact
"wolf in a valley" framing.

- **Accepted examples:** a small person walking across a desert; a
  small boat on open water; a distant car on a road; a small animal in
  an open field; a climber on a mountainside.
- **Not accepted:** a landscape/vista with no subject at all; a subject
  framed close/large with only the background being wide (this is the
  inverse of what the category targets); a subject too small/blurred
  to be identifiable at all (that would test something else - image
  quality at extreme distance, not scale/framing comprehension).

**Attribute tags:** `subject_human`, `subject_animal`, `subject_vehicle`,
`subject_boat`, `distance_far`, `distance_mid`, `backdrop_mountain`,
`backdrop_plain`, `backdrop_urban`, `backdrop_water`, `day`, `dusk`.

**Composition target:** 150-200 clips total. Minimum 100+ clips with a
clearly identifiable small subject; of those, at least 70% should have
the subject occupying roughly under ~20-25% of frame area (a looser,
more measurable bar than v1.0's "~15% of frame height," chosen because
it's easier to eyeball consistently during manual curation across
different subject types).

**Captioning:** hand-verified, same reasoning as category A - the
training signal depends on precise language, not just a correct image.
Every caption must contain explicit scale/distance language: "far
away," "in the distance," "a small figure," "a tiny boat/car/person" -
matched to what's actually visible, not templated identically across
every clip.

### C. `dense_architecture` - 100 clips

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
than 100 near-identical daytime skyscraper shots. Bias toward aerial
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

### E. `animals_regression_guard` - 100 clips

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

### Total: 600-650 clips (150+150-200+100+100+100) - "Dataset v1"

## 4a. Stage 0 comes before Dataset v1 (do this first)

Per explicit project decision, the 600-clip Dataset v1 is not built
before the training path itself is proven to work at all. **Stage 0**
is one combined step, 10-20 clips per category (50-100 total), same
quality bar and tagging taxonomy as Section 4, scaled down:

1. Source and quality-check 10-20 clips per category (50-100 total)
   from the sources verified in Section 5/6.
2. Run `ingest_dataset.py --rights-cleared`.
3. Check metadata (`ffprobe` fields sane?).
4. Verify captions (do categories A/B's captions actually contain the
   count/distance language Section 7 requires?).
5. Confirm the train/val/test split is deterministic (re-running
   ingestion on the same clips must produce the identical split -
   `DatasetManager`'s own guarantee, worth confirming once on real
   data, not just trusting the unit tests).
6. Run the shortest real LoRA experiment (per
   `docs/EXECUTION_PLAN_FIRST_GPU_RUN.md`, ~50-100 steps, free-tier
   GPU), then run a small benchmark comparison via
   `Wan22EvaluationHook` against the untrained baseline.

**The one question this answers:** does the training pipeline (real
weights -> real dataset -> real LoRA step -> real checkpoint) actually
run, and does it measurably change Wan2.2's behavior at all, in either
direction? Not "is the model better yet" - just "is it learnable."
This is the cheapest possible real signal before sourcing the full 600.
No new categories, no new analysis phase - this is the step the whole
project has been building toward.

## 5. Sources (free, openly-licensed only - multiple, each independently verified)

Pexels and Pixabay are REJECTED (Section 6) - both explicitly ban
automated collection for machine learning purposes. A paid
AI-training-licensed marketplace (Wirestock etc.) was considered and
deliberately **not** pursued - this project improves an existing model
for internal use, it is not building a commercial dataset-licensing
relationship, so "free and openly-licensed" is the right constraint,
not "whichever paid vendor's terms are cleanest."

Four real candidates, each with a genuinely different license
mechanism - not five near-identical general stock sites, since two of
those already failed for the same reason:

1. **Wikimedia Commons (video).** Site-wide upload policy accepts only
   CC-BY, CC-BY-SA, CC0/public-domain, or GFDL - Non-Commercial (NC) and
   No-Derivatives (ND) licenses are not allowed to be uploaded at all.
   Per Creative Commons' own May 2025 official guidance, CC-BY and CC0
   works generally permit AI/ML training (CC-BY needs attribution
   recorded, satisfiable by keeping a per-clip source-credit list).
   CC-BY-SA carries a real, still-debated legal question (do
   share-alike obligations propagate to a trained model's weights?) -
   treat CC-BY-SA clips as lower priority until that's resolved, prefer
   CC-BY/CC0-tagged files. Each file's exact license is on its own
   description page and must be recorded per-clip (not assumed from
   the site-wide policy). Practical caveat, not a legal one: Commons'
   video collection is much smaller than its image collection - actual
   availability per category (Section 4) needs a real scoping check,
   not just a legal green light.
2. **NASA Image and Video Library.** NASA content is generally not
   copyrightable in the US (work of the US federal government) - broad
   reuse, including commercial, is explicitly permitted. Two real
   carve-outs: the NASA insignia/logo may not be used, and any footage
   with an identifiable person needs that person's own permission for
   commercial use (rare in NASA's own launch/facility/Earth-observation
   footage). No ML-specific restriction found. Good fit for
   `wide_anchor_camera` (Category D) and parts of `dense_architecture`
   (facility/aerial shots) - not useful for `multi_entity_interaction`
   or `animals_regression_guard`.
3. **Internet Archive - public-domain/CC subcollections only, not the
   whole site.** Internet Archive hosts a huge mix of content with
   wildly varying rights (including plenty of unclear/uncleared
   uploads) - it is **not** blanket-clean the way Wikimedia Commons'
   upload policy is. The safe subset is its curated public-domain and
   Creative-Commons-tagged film collections (e.g. `archive.org/details/
   public-domain`, `publicmovies212`) - every clip's individual license
   tag still needs recording per-clip, same as Wikimedia Commons.
4. **Vimeo - individually CC-licensed creator uploads via Vimeo's own
   Creative Commons filter, NOT Vimeo Stock Footage.** Important
   distinction found during verification: Vimeo's paid "Stock Footage"
   marketplace explicitly **prohibits** ML/AI use in its own terms -
   that marketplace is out. Separately, individual creators on regular
   Vimeo can opt into a CC license for their own uploads, searchable via
   Vimeo's CC filter; those clips are governed by the CC license itself
   (point 1's CC-BY/CC0 reasoning applies), not Vimeo's stock-footage
   terms. Must verify per-video which license the specific uploader
   chose - CC filter search surfaces the license type but each clip's
   actual page should be checked before use.

**Explicitly not pursued further (checked, ruled out):** Videvo -
inconclusive from search, and given it's a general "free stock" site in
the same category as Pexels/Pixabay (both of which turned out to
restrict ML use), not worth a direct-fetch attempt without a stronger
signal it differs. Vevo and Vimeo Stock Footage - explicitly checked
and explicitly prohibit AI/ML use (Section 6).

**Open item, not yet done:** per-category availability scoping (can we
actually find ~100-150 clips per Section 4 category on these 4 sources
combined?) is a real research task, separate from the legal check
above - a source can be perfectly legal and still not have enough
"three people fighting" footage. Recommended before any real download
starts.

## 6. License verification log

Every entry cites the specific clause/date checked - not a general
impression of the platform's reputation. `REJECTED` means this project
does not use the source for pilot dataset clips; it does not mean the
platform is bad, just that its terms do not cover this specific use.
`CONDITIONALLY APPROVED` means usable, but per-clip license recording
is still required before `rights_cleared=True`.

| Date checked | Source | Relevant clause (verbatim) | AI training explicitly allowed | Decision |
|---|---|---|---|---|
| 2026-08-04 | Pexels | "Data mining, extraction, scraping and the use of programs or robots for automatic data collection and/or extraction of digital data on the Service and/or the content available therein is strictly prohibited for all unauthorised purposes, including without limitation for machine learning purposes." (Pexels Terms of Service, via help.pexels.com's AI/ML FAQ and pexels.com/terms-of-service) | **NO** - explicitly prohibited for bulk/automated ML use without Pexels' prior explicit permission | **REJECTED** |
| 2026-08-04 | Pixabay | "Data mining, extraction, scraping and the use of programs or robots for automatic data collection and/or extraction of digital data for machine learning purposes is strictly prohibited." Separately: "Pixabay content ... can't be used to train machine learning models or incorporated into AI generation tools ... redistribution for machine learning or database-building purposes isn't permitted under the license." (pixabay.com/service/terms/, pixabay.com/service/license-summary/) | **NO** - explicitly prohibited, applies to all content including AI-generated uploads | **REJECTED** |
| 2026-08-04 | Vimeo Stock Footage (paid marketplace) | "[Vimeo Stock Footage] prohibits licensees from using licensed works for any machine learning and/or artificial intelligence purposes, or in connection with any technologies designed for identification of natural persons." (vimeo.com/legal/service-terms/stock) | **NO** - explicitly prohibited | **REJECTED** (this marketplace only - regular Vimeo CC-licensed creator uploads are a separate, un-rejected case, see below) |
| 2026-08-04 | Wikimedia Commons (per site-wide upload policy; per-file license still required) | Upload policy requires CC-BY, CC-BY-SA, CC0/PD, or GFDL only - "must not include Non-Commercial (nc) or No-Derivatives (nd) restrictions." Creative Commons' own May 2025 guidance: "AI training is often permitted by copyright... CC-BY... CC0... [releases] into the public domain." | **YES, for CC-BY/CC0-tagged files** (CC-BY-SA: legally ambiguous re: share-alike propagation to model weights - deprioritize) | **CONDITIONALLY APPROVED** - CC-BY/CC0 files only, record each file's actual license before ingest |
| 2026-08-04 | NASA Image and Video Library | "NASA content... generally are not subject to copyright in the United States [as] works created by the U.S. federal government." Carve-outs: NASA insignia/logo, and identifiable-person footage needs that person's permission for commercial use. | **YES** (no ML-specific restriction found; general public-domain reuse, including commercial) | **CONDITIONALLY APPROVED** - avoid insignia/logo shots and any identifiable-person footage |
| 2026-08-04 | Internet Archive (public-domain/CC subcollections specifically, not the whole site) | Site hosts curated public-domain and CC-tagged film subcollections alongside large amounts of unrelated/unclear-rights content - not blanket-clean. | **YES, for items individually tagged public-domain/CC** - **NO / UNKNOWN for the rest of the site** | **CONDITIONALLY APPROVED** - curated PD/CC subcollections only, verify each item's own rights tag |
| 2026-08-04 | Vimeo (individual creator CC-licensed uploads via the CC filter, separate from Stock Footage above) | Governed by whichever CC license the individual creator selected (same CC-BY/CC0/CC-BY-SA reasoning as Wikimedia Commons row) | **YES, for CC-BY/CC0-tagged uploads** | **CONDITIONALLY APPROVED** - verify the specific license on each video's own page before use |

**Note on verification method:** every row was checked via direct web
search of the platform's own published terms/policy pages on
2026-08-04, not inferred from general reputation. Pexels' and
Pixabay's own help centers each have a page specifically about AI/ML
use - itself a signal this exact question comes up often enough to
need one, a real industry-wide 2026 trend. This project's
`rights_cleared` field stays `False` for every clip until its specific
source clip's own license is individually recorded, even for
"CONDITIONALLY APPROVED" sources - per `DatasetValidator`'s existing
hard rule, an unrights-cleared clip is a validation error, not a soft
warning.

## 7. Captioning approach

`training.dataset.captions.HeuristicCaptionProvider` (real, already
built) can produce a first-pass caption for every clip. For categories
A and B specifically (Section 4), heuristic captions are **not
sufficient on their own** - the training signal those two categories
exist to provide depends on precise count/distance language that a
generic heuristic captioner is unlikely to reliably produce. Plan:
heuristic pass first for all 600 clips, then a hand-verification pass
focused on categories A and B (300 clips) to confirm/correct the
count/distance language before `ingest_dataset.py` runs. Categories
C/D/E can rely on the heuristic pass alone for Dataset v1.

## 8. Explicit non-goals for v1.0

- Not attempting full category coverage of the original 30-category
  benchmark - only the categories tied to a real diagnosed weakness (or
  the one regression-guard category).
- Not using paid stock/AI-training-licensed marketplaces (Section 5) -
  free, openly-licensed sources only.
- Not targeting 5k-10k+ scale yet (Section 9).
- Not writing final captions by hand for all 600 clips - only the two
  categories where precision matters most for the training signal.

## 9. Phase gates (staged, each gated on the previous one's real evidence)

1. **Stage 0 (50-100 clips, Section 4a) -> Dataset v1 (600 clips,
   Section 4).** Gate: `ingest_dataset.py` runs cleanly end to end on
   real data (real metadata, real captions, a real deterministic split
   confirmed by re-running ingestion), AND a ~50-100-step LoRA run on
   the Stage 0 clips measurably changes the model's behavior at all
   (any direction) versus the untrained baseline, per
   `Wan22EvaluationHook`. If nothing changes, diagnose why before
   sourcing the rest of the 600 - it may be too few steps, too small a
   LoRA rank, or a real backend issue, not necessarily "need more data."
2. **Dataset v1 (600 clips) -> Phase 2 (5k-10k).** Gate: the Dataset v1
   LoRA shows a real, visually-confirmed improvement - not just a CLIP
   delta - on at least one of categories A or B's exact failure cases
   (a 3-entity prompt rendering a real 3rd entity; a wide shot actually
   rendering its subject small/distant), checked via
   `Wan22EvaluationHook` + `RegressionDetector` against the untrained
   baseline, with no regression on category E
   (`animals_regression_guard`).
3. **Phase 2 -> Phase 3 (50k-100k).** Not designed yet - deliberately
   out of scope until gate 2 is actually cleared with real evidence.

At every gate, "scale the dataset further" is not the automatic answer
to a disappointing result - Stage 0 in particular exists so a pipeline
or config problem gets caught at 50-100-clip cost, not diagnosed for
the first time after 600 clips are already sourced.
