#!/usr/bin/env python3
"""Wan2.2 LoRA training entrypoint.

This is the training entrypoint script ADR 0022 identified as the one
missing piece blocking `run_experiment.py --dispatch` - what a Kaggle
kernel's `code_file` or a Modal `app_entrypoint` actually runs.

It wires together, for real: `TrainingConfig` loading, a pre-built
Wan2.2 dataset manifest (`training.wan22.load_manifest_jsonl`),
`Wan22LoRAConfig` (both-experts-paired-by-construction for the A14B
variants), a `FilesystemCheckpointStore` + `Wan22CheckpointWriter`, and
`Wan22LoRATrainer`. The one piece that is NOT real is the training
backend: `IWan22TrainingBackend`'s only implementation
(`UnavailableWan22Backend`) raises `ModelUnavailableError` the instant a
real step is attempted, because no GPU, no downloaded Wan2.2 weights,
and no diffusers/musubi-tuner integration exist in this environment.

Running this script today always ends in a clean, reported failure
(exit code 1, a `ModelUnavailableError` message, no partial/corrupt
checkpoints written) - that is the deliberate, correct behavior until a
real backend is plugged in behind `IWan22TrainingBackend`. See
docs/adr/0023-wan22-training-execution-layer.md.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from training import (
    FilesystemCheckpointStore,
    TrainingConfig,
    UnavailableWan22Backend,
    Wan22CheckpointWriter,
    Wan22LoRAConfig,
    Wan22LoRATrainer,
    load_manifest_jsonl,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", required=True, type=Path, help="TrainingConfig YAML for this run")
    parser.add_argument(
        "--dataset-manifest", required=True, type=Path,
        help="JSONL manifest built via Wan22DatasetAdapter.write_manifest_jsonl()",
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--checkpoint-store-dir", required=True, type=Path)
    parser.add_argument("--job-id", required=True, help="training.automation JobRecord id, for log correlation")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    config = TrainingConfig.from_yaml(args.config)
    config.validate()

    if not args.dataset_manifest.exists():
        print(f"[{args.job_id}] dataset manifest not found: {args.dataset_manifest}", file=sys.stderr)
        return 1
    entries = load_manifest_jsonl(args.dataset_manifest)
    if not entries:
        print(f"[{args.job_id}] dataset manifest {args.dataset_manifest} is empty", file=sys.stderr)
        return 1

    try:
        lora_config = Wan22LoRAConfig.from_training_config(config)
    except ValueError as exc:
        print(f"[{args.job_id}] invalid LoRA configuration: {exc}", file=sys.stderr)
        return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_store = FilesystemCheckpointStore(args.checkpoint_store_dir)
    checkpoint_writer = Wan22CheckpointWriter(checkpoint_store)
    backend = UnavailableWan22Backend()

    trainer = Wan22LoRATrainer(
        backend=backend,
        checkpoint_writer=checkpoint_writer,
        dataset_entries=entries,
        lora_config=lora_config,
        output_dir=args.output_dir,
        on_step=lambda step: print(f"[{args.job_id}] step {step}/{config.max_train_steps}"),
    )

    print(
        f"[{args.job_id}] starting Wan2.2 LoRA training run {config.run_id} "
        f"(base_model={config.base_model_id}, experts={sorted(lora_config.experts)}, "
        f"{len(entries)} dataset entries)"
    )
    result = trainer.train(config)
    print(f"[{args.job_id}] run {result.run_id} ended with status={result.status} at step={result.final_step}")
    if result.error_message:
        print(f"[{args.job_id}] error: {result.error_message}", file=sys.stderr)
    return 0 if result.status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
