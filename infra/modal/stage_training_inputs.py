#!/usr/bin/env python3
"""Stages one real training job's inputs (config.yaml, dataset_manifest.jsonl,
and every real clip file the manifest references) onto the persistent
Modal Volume ("wan22-training-data") that
services/training/entrypoints/modal_wan22_train_app.py's `train_wan22_lora`
function mounts at /vol - then validates every uploaded path is really
there.

Real, concrete reason this exists: `TrainingCommand.to_modal_extra_args()`
passes `--config`/`--dataset-manifest` as bare local path strings, the
same contract used for a local subprocess or a Kaggle kernel (where
those files already exist on that machine's own filesystem). Modal's
CLI does not auto-upload a local file referenced by a plain string
argument - so by the time `train_wan22_lora` runs, `config`/
`dataset_manifest` must already point at real files on ITS OWN Volume,
not this script's local filesystem. This script is that real,
necessary staging step - see
services/training/entrypoints/modal_wan22_train_app.py's own module
docstring for the full context.

Deliberately does NOT call `modal run` and does NOT touch dispatch.py,
command.py, wan22_lora_train.py, or download_wan22_weights.py - no GPU
is requested and no training runs anywhere in this script. It only
uploads files and reads them back to confirm they landed.

Real manifest entries hold a `video_path` field
(training.wan22.dataset_adapter.Wan22ManifestEntry) that
diffusers_backend.py later reads directly off the local filesystem
(`imageio.imread(entry.video_path)`) - so the manifest this script
actually uploads is a real, byte-for-byte copy of the input manifest
with every `video_path` rewritten to the real Volume path its
corresponding clip is uploaded to, not the original local path (which
won't exist inside a Modal container).

Usage:
    uv run --with modal python infra/modal/stage_training_inputs.py \\
        --config .training-data/ci_smoke_config.yaml \\
        --dataset-manifest .training-data/manifests/<version>_train.jsonl \\
        --dataset-version <version> \\
        --job-id modal-smoke-prep
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import modal

_VOLUME_NAME = "wan22-training-data"
# Must match modal_wan22_train_app.py's own _VOLUME_MOUNT_PATH exactly -
# this is the path the real training container will see this same
# Volume mounted at.
_VOLUME_MOUNT_PATH = "/vol"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--dataset-manifest", required=True, type=Path)
    parser.add_argument("--dataset-version", required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--volume-name", default=_VOLUME_NAME)
    return parser


def _rewrite_manifest_for_volume(
    local_manifest_path: Path, job_id: str,
) -> tuple[Path, list[dict], list[tuple[Path, str]]]:
    """Reads the real manifest, verifies every referenced clip really
    exists locally (a broken/unresolvable path fails here, before any
    upload is attempted), and writes a rewritten copy whose `video_path`
    values point at the real Volume path each clip will be uploaded to.
    Returns (rewritten_manifest_path, original_entries, [(local_clip,
    volume_clip_relpath), ...])."""
    entries = [json.loads(line) for line in local_manifest_path.read_text().splitlines() if line.strip()]
    if not entries:
        raise ValueError(f"{local_manifest_path} has no entries - nothing to stage")

    clip_uploads: list[tuple[Path, str]] = []
    rewritten_lines: list[str] = []
    for entry in entries:
        local_clip_path = Path(entry["video_path"])
        if not local_clip_path.is_file():
            raise FileNotFoundError(
                f"Manifest entry references a clip that does not exist locally: {local_clip_path} "
                f"(broken/unresolvable path - refusing to upload a manifest that would fail the same "
                f"way once training tries to read it)"
            )
        volume_clip_relpath = f"runs/{job_id}/clips/{local_clip_path.name}"
        clip_uploads.append((local_clip_path, volume_clip_relpath))
        rewritten_entry = dict(entry)
        rewritten_entry["video_path"] = f"{_VOLUME_MOUNT_PATH}/{volume_clip_relpath}"
        rewritten_lines.append(json.dumps(rewritten_entry))

    rewritten_path = local_manifest_path.parent / f"{local_manifest_path.stem}.volume-paths.jsonl"
    rewritten_path.write_text("\n".join(rewritten_lines) + "\n")
    return rewritten_path, entries, clip_uploads


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if not args.config.is_file():
        print(f"--config not found: {args.config}", file=sys.stderr)
        return 1
    if not args.dataset_manifest.is_file():
        print(f"--dataset-manifest not found: {args.dataset_manifest}", file=sys.stderr)
        return 1

    rewritten_manifest_path, entries, clip_uploads = _rewrite_manifest_for_volume(
        args.dataset_manifest, args.job_id,
    )

    config_relpath = f"runs/{args.job_id}/config.yaml"
    manifest_relpath = f"runs/{args.job_id}/dataset_manifest.jsonl"

    print(f"Staging job {args.job_id!r} onto Modal Volume {args.volume_name!r}:")
    print(f"  config: {args.config} -> {_VOLUME_MOUNT_PATH}/{config_relpath}")
    print(f"  manifest (rewritten video_path values): {rewritten_manifest_path} -> {_VOLUME_MOUNT_PATH}/{manifest_relpath}")
    for local_clip, volume_relpath in clip_uploads:
        print(f"  clip: {local_clip} -> {_VOLUME_MOUNT_PATH}/{volume_relpath}")

    volume = modal.Volume.from_name(args.volume_name, create_if_missing=True)
    with volume.batch_upload(force=True) as batch:
        batch.put_file(str(args.config), config_relpath)
        batch.put_file(str(rewritten_manifest_path), manifest_relpath)
        for local_clip, volume_relpath in clip_uploads:
            batch.put_file(str(local_clip), volume_relpath)
    volume.commit()
    print("\nUpload complete, Volume committed.")

    print(f"\nValidating: listing real Volume contents under runs/{args.job_id}/ ...")
    real_entries = volume.listdir(f"runs/{args.job_id}", recursive=True)
    real_paths = {e.path.lstrip("/") for e in real_entries}
    for e in sorted(real_entries, key=lambda x: x.path):
        print(f"  {e.path}  ({e.size} bytes)")

    expected_paths = {config_relpath, manifest_relpath} | {vp for _, vp in clip_uploads}
    missing = sorted(expected_paths - real_paths)
    validation_ok = not missing and len(clip_uploads) == len(entries)

    print("\n=== SUMMARY ===")
    print(f"dataset_version: {args.dataset_version}")
    print(f"job_id: {args.job_id}")
    print(f"config (local): {args.config}")
    print(f"config (Volume): {_VOLUME_MOUNT_PATH}/{config_relpath}")
    print(f"manifest (local): {args.dataset_manifest}")
    print(f"manifest (Volume, rewritten): {_VOLUME_MOUNT_PATH}/{manifest_relpath}")
    print(f"clip count (expected): {len(entries)}")
    print(f"clip count (uploaded): {len(clip_uploads)}")
    print(f"real files found on Volume under runs/{args.job_id}/: {len(real_paths)}")
    print(f"missing on Volume: {missing if missing else 'none'}")
    print(f"validation result: {'PASS' if validation_ok else 'FAIL'}")
    print("modal run ...::train_wan22_lora: NOT executed - no GPU, no training in this script.")

    return 0 if validation_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
