#!/usr/bin/env python3
"""Downloads one Wan2.2 engine's real weights from Hugging Face Hub, per
its `download:` block in `models/registry.yaml`, and records a
per-file SHA-256 checksum manifest under `.models-cache/<engine_id>/`
(see `training.hf_download`).

This is a real, network-touching operation - it is not automated by any
GitHub Actions workflow in this repository (weights are multi-GB and do
not belong in CI). Run it manually, once, on the machine/environment
that will actually run training (see docs/EXECUTION_PLAN_FIRST_GPU_RUN.md).

Requires:
  - the training[gpu-training] extra installed
    (`uv sync --all-packages --extra gpu-training`)
  - network access to huggingface.co
  - HF_TOKEN set in the environment if the target repo is gated
    (Wan-AI's Wan2.2 Diffusers repos are public as of this writing, so
    this is usually not required - see the repo's own HF page)
"""

from __future__ import annotations

import argparse
import os
import sys

from training import HFDownloadError, HuggingFaceWeightsDownloader, load_wan22_registry_entries, validate_wan22_registry_entry


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--engine-id", required=True,
        help="e.g. wan2.2-ti2v-5b or wan2.2-t2v-a14b - must have a download: block in --registry",
    )
    parser.add_argument("--registry", default="models/registry.yaml")
    parser.add_argument("--cache-root", default=".models-cache")
    parser.add_argument("--force", action="store_true", help="Re-download even if a verified cache already exists")
    parser.add_argument(
        "--hf-token", default=None,
        help="Defaults to the HF_TOKEN environment variable; only needed for gated repos",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    entries = load_wan22_registry_entries(args.registry)
    entry = entries.get(args.engine_id)
    if entry is None:
        print(
            f"No Wan2.2 registry entry with a download: block found for engine_id={args.engine_id!r} "
            f"in {args.registry}. Known entries: {sorted(entries)}",
            file=sys.stderr,
        )
        return 1

    validation = validate_wan22_registry_entry(entry)
    if not validation.valid:
        print(f"Registry entry for {args.engine_id!r} failed validation:", file=sys.stderr)
        for issue in validation.issues:
            print(f"  [{issue.severity}] {issue.field}: {issue.message}", file=sys.stderr)
        return 1

    print(
        f"Downloading {entry.download.repo_id}@{entry.download.revision} for {args.engine_id} "
        f"(~{entry.download.approx_download_size_gb:g}GB, allow_patterns={list(entry.download.allow_patterns)}) "
        f"into {args.cache_root}/{args.engine_id}/ ..."
    )
    downloader = HuggingFaceWeightsDownloader(
        cache_root=args.cache_root, hf_token=args.hf_token or os.environ.get("HF_TOKEN"),
    )
    try:
        manifest = downloader.download(entry, force=args.force)
    except HFDownloadError as exc:
        print(f"Download failed: {exc}", file=sys.stderr)
        return 1

    print(f"Downloaded {len(manifest.files)} files to {manifest.local_dir}")
    print("Verifying checksums...")
    manifest.verify()
    print(f"OK - {args.engine_id} weights are ready at {manifest.local_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
