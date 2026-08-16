#!/usr/bin/env python3
"""Controlled, zero-cost smoke test for the Wan2.2 training pipeline -
run and pass this before spending anything on a real GPU experiment
(see docs/EXECUTION_PLAN_FIRST_GPU_RUN.md).

Exercises the REAL mechanism end-to-end, entirely on CPU, in seconds,
with $0 cost and no downloaded weights:

  TrainingConfig -> Wan22LoRAConfig -> Wan22LoRATrainer ->
  Wan22DiffusersBackend (real diffusers.WanTransformer3DModel + real
  peft LoRA injection + a real forward/backward/AdamW step, at a tiny
  randomly-initialized scale) -> Wan22CheckpointWriter -> paired
  checkpoint verification.

If `ffmpeg` is on PATH, real tiny synthetic clips are generated and run
through the full, real `DatasetManager` pipeline (ffprobe metadata
extraction, captioning, validation, split, dataset versioning) first -
the same dataset-pipeline path `ingest_dataset.py` uses on real footage.
If `ffmpeg` is not available, that stage is skipped (clearly reported)
and the trainer runs directly against hand-built `Wan22ManifestEntry`
records instead - the training-mechanism smoke test itself does not
depend on ffmpeg.

Requires the training[gpu-training] extra
(`uv sync --all-packages --extra gpu-training`); exits 1 if it is not
installed.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from training import (
    DatasetManager,
    DatasetValidator,
    FilesystemCheckpointStore,
    FilesystemDatasetVersionStore,
    HashDuplicateDetector,
    HeuristicCaptionProvider,
    LoRAConfig,
    ModelUnavailableError,
    TrainingConfig,
    Wan22CheckpointWriter,
    Wan22DatasetAdapter,
    Wan22LoRAConfig,
    Wan22LoRATrainer,
    Wan22ManifestEntry,
    build_smoke_test_backend,
)

_NUM_CLIPS = 2
_CLIP_DURATION_SEC = 1.0
_CLIP_SIZE = "64x64"
_CLIP_FPS = 8


def _make_ffmpeg_clip(path: Path, color: str) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", f"color=c={color}:size={_CLIP_SIZE}:duration={_CLIP_DURATION_SEC}:rate={_CLIP_FPS}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
        ],
        check=True,
    )


def _build_manifest_entries_via_real_dataset_pipeline(tmp_dir: Path, config: TrainingConfig) -> list[Wan22ManifestEntry]:
    print("ffmpeg found - running the real DatasetManager pipeline (ffprobe, caption, validate, split)...")
    manager = DatasetManager(
        validator=DatasetValidator(min_duration_sec=0.1, min_height=32, min_fps=1.0),
        caption_provider=HeuristicCaptionProvider(),
        duplicate_detector=HashDuplicateDetector(),
    )
    colors = ["red", "green", "blue"][:_NUM_CLIPS]
    for i, color in enumerate(colors):
        clip_path = tmp_dir / f"clip_{i}_{color}.mp4"
        _make_ffmpeg_clip(clip_path, color)
        manager.ingest(str(clip_path), tags=[color, "smoke-test"], rights_cleared=True)
    manager.caption_all()

    validation_results = manager.validate_all()
    for clip_id, result in validation_results.items():
        for issue in result.issues:
            if issue.severity == "error":
                raise RuntimeError(f"smoke-test clip {clip_id} failed validation: {issue.message}")

    manager.split(val_fraction=0.0, test_fraction=0.0, seed=0)
    dataset_version = manager.version()
    FilesystemDatasetVersionStore(tmp_dir / "dataset-versions").save(dataset_version)
    print(f"  real dataset_version: {dataset_version.version_id} ({dataset_version.statistics.clip_count} clips)")

    adapter = Wan22DatasetAdapter(config)
    return adapter.build_manifest([r for r in manager.records() if r.split == "train"], split="train")


def _build_manifest_entries_synthetic() -> list[Wan22ManifestEntry]:
    print("ffmpeg not found - skipping the real DatasetManager stage; using hand-built manifest entries.")
    return [
        Wan22ManifestEntry(
            clip_id=f"smoke_clip_{i}", video_path=f"/synthetic/{i}.mp4", caption="a synthetic smoke-test clip",
            width=64, height=64, num_frames=9, fps=8.0,
        )
        for i in range(_NUM_CLIPS)
    ]


def _build_smoke_config(base_model_id: str, max_train_steps: int, seed: int) -> TrainingConfig:
    config = TrainingConfig(
        schema_version="1.0", run_id="smoke-test", base_model_id=base_model_id, base_model_revision="2.2.0",
        strategy="lora", dataset_version="smoke-test", resolution="64x64", fps=8, max_frames=9,
        learning_rate=1e-3, batch_size=1, gradient_accumulation_steps=1, max_train_steps=max_train_steps,
        mixed_precision="no", min_vram_gb=1.0, gpu_count=1, checkpoint_every_steps=max(1, max_train_steps // 2),
        eval_every_steps=max(1, max_train_steps // 2), seed=seed,
        lora=LoRAConfig(rank=4, alpha=8, target_modules=("to_q", "to_k", "to_v", "to_out.0"), dropout=0.0),
        notes="Controlled smoke test - not a real training run.",
    )
    config.validate()
    return config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--base-model-id", default="wan2.2-ti2v-5b", choices=["wan2.2-ti2v-5b", "wan2.2-t2v-a14b", "wan2.2-i2v-a14b"],
    )
    parser.add_argument("--max-train-steps", type=int, default=4)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--keep-workdir", action="store_true", help="Do not delete the temp working directory")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = _build_smoke_config(args.base_model_id, args.max_train_steps, args.seed)
    lora_config = Wan22LoRAConfig.from_training_config(config)

    workdir = Path(tempfile.mkdtemp(prefix="sallehly-wan22-smoke-"))
    try:
        if shutil.which("ffmpeg") is not None:
            entries = _build_manifest_entries_via_real_dataset_pipeline(workdir, config)
        else:
            entries = _build_manifest_entries_synthetic()

        try:
            backend = build_smoke_test_backend(base_model_id=config.base_model_id, seed=args.seed)
        except ModelUnavailableError as exc:
            print(f"Cannot run the smoke test: {exc}", file=sys.stderr)
            print(
                "Install the training[gpu-training] extra: "
                "uv sync --all-packages --extra gpu-training",
                file=sys.stderr,
            )
            return 1

        checkpoint_store = FilesystemCheckpointStore(workdir / "checkpoints")
        checkpoint_writer = Wan22CheckpointWriter(checkpoint_store)
        trainer = Wan22LoRATrainer(
            backend=backend, checkpoint_writer=checkpoint_writer, dataset_entries=entries,
            lora_config=lora_config, output_dir=workdir / "output",
            on_step=lambda step: print(f"  step {step}/{config.max_train_steps}"),
        )

        print(
            f"Running smoke test: base_model={config.base_model_id}, experts={sorted(lora_config.experts)}, "
            f"{len(entries)} entries, {config.max_train_steps} steps (real tiny WanTransformer3DModel + real "
            "peft LoRA, CPU, ~seconds)..."
        )
        result = trainer.train(config)

        if result.status != "completed":
            print(f"SMOKE TEST FAILED: status={result.status} error={result.error_message}", file=sys.stderr)
            return 1

        for checkpoint_id in result.checkpoint_ids:
            record = checkpoint_store.get(checkpoint_id)
            artifact_path = Path(record.artifact_uri.removeprefix("file://"))
            if not artifact_path.exists():
                print(f"SMOKE TEST FAILED: checkpoint {checkpoint_id} artifact missing: {artifact_path}", file=sys.stderr)
                return 1

        print(
            f"SMOKE TEST PASSED: {result.final_step} steps, {len(result.checkpoint_ids)} checkpoint(s) saved "
            f"and verified on disk. The wiring is correct - this did NOT validate real Wan2.2 output quality "
            "(tiny random weights, no real weights or GPU involved). See docs/EXECUTION_PLAN_FIRST_GPU_RUN.md "
            "for what's needed before a real GPU run."
        )
        return 0
    finally:
        if args.keep_workdir:
            print(f"Kept working directory: {workdir}")
        else:
            shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
