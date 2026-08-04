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

## One command (run on a machine with real network access)

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
