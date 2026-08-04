#!/usr/bin/env python3
"""Turns a directory of raw video clips into the first real dataset
version: real `ffprobe` metadata + SHA-256 hashing (`DatasetManager.ingest`),
real heuristic captioning, real validation (rights clearance, duration/
resolution/fps floors), real deterministic train/val/test split, a real
content-addressable `dataset_version` id, and a Wan2.2 training manifest
JSONL per split - the concrete answer to "how do I go from a folder of
clips to something `TrainingConfig.dataset_version` and
`wan22_lora_train.py --dataset-manifest` can actually consume."

This is the one step in the pipeline that requires a human decision this
script will not make for you: `--rights-cleared` must be passed
explicitly (there is no default) because `DatasetValidator` treats an
undocumented rights chain as a hard validation error, by design - see
services/training/src/training/dataset/validator.py.

Real, CPU-only, $0 - requires `ffprobe` on PATH (already required by
`training-phase1-dataset-validation.yml`), nothing from the
`gpu-training` extra.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from training import (
    DatasetManager,
    DatasetValidator,
    FilesystemDatasetVersionStore,
    HashDuplicateDetector,
    HeuristicCaptionProvider,
    Wan22DatasetAdapter,
    TrainingConfig,
)

_VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".mkv", ".webm"})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--clips-dir", required=True, type=Path, help="Directory of raw video clip files")
    parser.add_argument(
        "--rights-cleared", action="store_true",
        help="Assert that every clip under --clips-dir has a documented, auditable rights chain. "
        "Required - there is no default. Do not pass this unless that is actually true.",
    )
    parser.add_argument("--tag", action="append", default=[], dest="tags", help="Repeatable; applied to every clip")
    parser.add_argument(
        "--tag-from-subdir", action="store_true",
        help="Also tag each clip with its immediate parent directory name relative to --clips-dir "
        "(e.g. <clips-dir>/multi_entity_interaction/clip1.mp4 gets an extra 'multi_entity_interaction' "
        "tag). Lets one invocation ingest several category subfolders into a single dataset_version "
        "with per-clip category tags, instead of running the script once per category. Clips directly "
        "under --clips-dir (no subfolder) get no extra tag from this flag.",
    )
    parser.add_argument("--val-fraction", type=float, default=0.1)
    parser.add_argument("--test-fraction", type=float, default=0.1)
    parser.add_argument("--split-seed", type=int, default=0)
    parser.add_argument("--version-store-dir", type=Path, default=Path(".training-data/dataset-versions"))
    parser.add_argument("--manifest-output-dir", type=Path, default=Path(".training-data/manifests"))
    parser.add_argument(
        "--base-model-config", type=Path, default=None,
        help="A TrainingConfig YAML (for max_frames) - required to build Wan2.2 manifests; "
        "omit to only ingest/validate/version without writing manifests",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if not args.rights_cleared:
        print(
            "Refusing to ingest: --rights-cleared was not passed. Every clip needs a documented, "
            "auditable rights chain before it may enter a training dataset - see "
            "services/training/src/training/dataset/validator.py.",
            file=sys.stderr,
        )
        return 1

    clip_paths = sorted(p for p in args.clips_dir.rglob("*") if p.suffix.lower() in _VIDEO_EXTENSIONS)
    if not clip_paths:
        print(f"No video files ({sorted(_VIDEO_EXTENSIONS)}) found under {args.clips_dir}", file=sys.stderr)
        return 1

    manager = DatasetManager(
        validator=DatasetValidator(),
        caption_provider=HeuristicCaptionProvider(),
        duplicate_detector=HashDuplicateDetector(),
    )

    print(f"Ingesting {len(clip_paths)} clip(s) from {args.clips_dir} ...")
    for path in clip_paths:
        clip_tags = list(args.tags)
        if args.tag_from_subdir and path.parent.resolve() != args.clips_dir.resolve():
            clip_tags.append(path.parent.name)
        record = manager.ingest(str(path), tags=clip_tags, rights_cleared=args.rights_cleared)
        tag_suffix = f" tags={clip_tags}" if clip_tags else ""
        print(f"  {record.clip_id}  {record.metadata.resolution}@{record.metadata.fps:g}fps  {path.name}{tag_suffix}")

    manager.caption_all()

    duplicates = manager.find_duplicates()
    if duplicates:
        print(f"Found {len(duplicates)} exact-duplicate clip pair(s) (same content, different filenames):")
        for a, b in duplicates:
            print(f"  {a} == {b}")

    validation_results = manager.validate_all()
    had_errors = False
    for clip_id, result in validation_results.items():
        for issue in result.issues:
            print(f"  [{issue.severity}] {clip_id}: {issue.field}: {issue.message}")
            if issue.severity == "error":
                had_errors = True
    if had_errors:
        print("One or more clips failed validation (see [error] lines above) - fix and re-run.", file=sys.stderr)
        return 1

    manager.split(val_fraction=args.val_fraction, test_fraction=args.test_fraction, seed=args.split_seed)

    dataset_version = manager.version()
    version_store = FilesystemDatasetVersionStore(args.version_store_dir)
    version_store.save(dataset_version)
    split_counts = dataset_version.statistics.split_counts
    print(f"\nDataset version: {dataset_version.version_id}  ({len(dataset_version.clip_ids)} clips)")
    print(
        f"  train={split_counts.get('train', 0)}  val={split_counts.get('val', 0)}  "
        f"test={split_counts.get('test', 0)}"
    )
    print(f"Saved to {args.version_store_dir}/{dataset_version.version_id}.json")

    if args.base_model_config is not None:
        config = TrainingConfig.from_yaml(args.base_model_config)
        adapter = Wan22DatasetAdapter(config)
        args.manifest_output_dir.mkdir(parents=True, exist_ok=True)
        for split in ("train", "val", "test"):
            split_records = [r for r in manager.records() if r.split == split]
            if not split_records:
                continue
            out_path = args.manifest_output_dir / f"{dataset_version.version_id}_{split}.jsonl"
            adapter.write_manifest_jsonl(split_records, out_path, split=split)
            print(f"Wrote {split} manifest ({len(split_records)} entries) to {out_path}")

    print(
        f"\nNext step: set dataset_version: {dataset_version.version_id} in your TrainingConfig YAML "
        "(replacing the REPLACE_WITH_REAL_DATASET_VERSION_ID placeholder)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
