# Stage 0 sources

Practical sourcing reference for Stage 0 (50-100 clips, 10-20 per
category - see `docs/DATASET_SPEC.md` Section 4a). Legal verification
for every source below is already done in `docs/DATASET_SPEC.md`
Section 6 - this file is the "where do I actually go look" companion,
not a second license review.

| Category | Source | Category/Search | Acceptance criteria |
|---|---|---|---|
| `multi_entity_interaction` | Wikimedia Commons | `Category:Videos of sports`, `Category:Videos of dance`, `Category:Group dances` | 3+ clearly distinguishable people, actively interacting (not just co-present) - combat, dance, team sport, coordinated work/play. Caption must name the real count in words. |
| `distant_small_subject` v1.1 | Wikimedia Commons, NASA | Commons: `Category:Aerial videos`, `Category:Drone videos of nature/mountains/bodies of water`. NASA: Earth-observation/aerial search on images.nasa.gov | A clearly identifiable subject (person/animal/vehicle/boat) occupying roughly under ~20-25% of frame area against a wide backdrop. Reject: no subject at all, or subject framed close/large. Caption must contain explicit scale/distance language. |
| `dense_architecture` | Wikimedia Commons | `Category:Videos from New York City` (and other-city equivalents), `Category:Skyscrapers` subcats (mostly stills - filter for actual video files) | A real building genuinely visible in motion footage, not a still photo. Mix of angle (aerial/street/oblique), day/night/weather per `docs/DATASET_SPEC.md` Section 4.C. |
| `wide_anchor_camera` | NASA, Wikimedia Commons | NASA: Earth/aerial library. Commons: `Category:Aerial videos`, `Category:Drone videos of nature` | One unambiguous compositional anchor (river, single structure, light source) in an otherwise wide/diffuse shot. |
| `animals_regression_guard` | Wikimedia Commons | `Category:Videos of animal behavior` (929 files - real count, confirmed 2026-08-04), `Category:Videos of Aves` (170 files) | Representative, non-adversarial - a clean, well-handled animal shot. No count/scale requirement (this category isn't fixing a weakness). |

## Folder structure (matches `ingest_dataset.py --tag-from-subdir`)

```
dataset/
  raw/                              # gitignored - never committed, machine-local only
    multi_entity_interaction/
    distant_small_subject/
    dense_architecture/
    wide_anchor_camera/
    animals_regression_guard/
```

Subfolder names must match the category tags in `docs/DATASET_SPEC.md`
Section 3 exactly - `ingest_dataset.py --tag-from-subdir` (added
alongside this file) auto-tags every clip with its immediate parent
folder name, so one ingest run covers all 5 categories with correct
per-clip tags and one shared, deterministic train/val/test split.

## Step 1: fetch clips (phone-friendly - a Kaggle notebook cell, no file management)

`dataset/sources/fetch_stage0.py` is written to be pasted into one
Kaggle notebook cell (or run as `python dataset/sources/fetch_stage0.py`
in a notebook terminal). It does not need file uploads or a separate
terminal - browsing and pasting URLs is the only manual step:

1. Browse each category's Wikimedia Commons / NASA pages (table above)
   in your phone's browser.
2. For each clip that looks right, copy its normal page URL (the
   Commons `File:...` page, or the NASA item/details page you're
   already viewing - not a special "copy video address").
3. Open `fetch_stage0.py`, paste 10 URLs per category into the
   `CATEGORY_URLS` dict near the top (the only part you edit).
4. Run it. It resolves each page URL to the real video file, downloads
   into `dataset/raw/<category>/` (folders created automatically - no
   `mkdir` step needed), and prints an `ffprobe` summary per file so
   you can sanity-check duration/resolution immediately.
5. Preview a few downloaded files in Kaggle's file browser and confirm
   each one still meets its category's acceptance criteria above
   (delete and re-source any that don't - the script fetches and
   reports, it cannot judge composition for you).

This was written without live network access to Wikimedia/NASA from
this session (see the file's own header note) - correct per their
documented API shapes and covered by `tests/test_dataset_fetch_stage0.py`
(mocked responses, 10/10 passing), but run it on one URL first and
check the printed output before pasting in all 50.

## Step 2: ingest (same command as before)

```bash
cd services/training
uv sync --all-packages
python scripts/ingest_dataset.py \
  --clips-dir ../../dataset/raw \
  --rights-cleared \
  --tag-from-subdir \
  --tag stage0 \
  --base-model-config configs/wan22_finetune.yaml
```

`--rights-cleared` is safe to pass here **only** because every clip
under `dataset/raw/` came from a source `docs/DATASET_SPEC.md` Section
6 marked `CONDITIONALLY APPROVED`, with that specific clip's own
license individually confirmed as CC-BY/CC0/public-domain (not
CC-BY-SA, not unverified) before it was placed in the folder - the
flag asserts a real, already-done check, not a formality to click
through.

Output: a `dataset_version` id printed at the end (paste into
`services/training/configs/wan22_finetune.yaml`'s `dataset_version`
field, replacing the placeholder) plus `train`/`val`/`test` manifest
JSONL files ready for `wan22_lora_train.py --dataset-manifest`.

## What this pipeline does NOT automate (by design)

Nothing here downloads video bytes automatically. Wikimedia Commons
and NASA both have real search APIs that could list candidate files
programmatically, but the acceptance criteria above (3+ people
*actively interacting*, subject *occupying ~20-25% of frame*, a real
building *in motion* vs. a still photo) are visual composition
judgments an API response can't make - a human has to actually look at
each candidate before it goes in `dataset/raw/`. Automating the
metadata/license side of this without automating the part that
requires actual human judgment was a deliberate choice, not a gap.
