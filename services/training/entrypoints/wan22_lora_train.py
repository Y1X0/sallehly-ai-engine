#!/usr/bin/env python3
"""Wan2.2 LoRA training entrypoint.

This is the training entrypoint script ADR 0022 identified as the one
missing piece blocking `run_experiment.py --dispatch` - what a Kaggle
kernel's `code_file` or a Modal `app_entrypoint` actually runs.

It wires together, for real: `TrainingConfig` loading, a pre-built
Wan2.2 dataset manifest (`training.wan22.load_manifest_jsonl`),
`Wan22LoRAConfig` (both-experts-paired-by-construction for the A14B
variants), a `FilesystemCheckpointStore` + `Wan22CheckpointWriter`, and
`Wan22LoRATrainer`.

The training backend (`--backend`) is now real by default
(docs/adr/0024-wan22-real-training-backend.md):

  - `real` (default when real weights are cached; see
    `training.hf_download.resolve_local_weights`): a
    `Wan22DiffusersBackend` loading actual `WanTransformer3DModel`
    weights per `models/registry.yaml`, with real `peft` LoRA injection
    and a real forward/backward/optimizer step.
  - `smoke-test`: the same real mechanism (real `WanTransformer3DModel`
    class, real LoRA, real backward pass) at a tiny randomly-initialized
    scale - runs on CPU in seconds, proves the wiring without needing
    real weights or a GPU. Auto-selected when no real weights are cached
    yet, so this script still runs to a real (if tiny-scale) completion
    out of the box rather than failing.
  - `unavailable`: the original `UnavailableWan22Backend` - always
    raises `ModelUnavailableError` on the first real call. Useful to
    explicitly prove "this run has no backend attached" (e.g. in a CI
    check) without needing the gpu-training extra installed at all.

Running this script requires the `training[gpu-training]` extra for
`--backend real` or `--backend smoke-test` (`uv sync --all-packages
--extra gpu-training`); `--backend unavailable` needs nothing beyond the
base `training` package.
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
    Wan22ModelSource,
    load_manifest_jsonl,
    load_wan22_registry_entries,
    resolve_local_weights,
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
    parser.add_argument(
        "--backend", choices=["auto", "real", "smoke-test", "unavailable"], default="auto",
        help="'auto' (default): real weights if cached (training.hf_download), else smoke-test.",
    )
    parser.add_argument("--registry", default="models/registry.yaml")
    parser.add_argument("--models-cache-root", default=".models-cache")
    parser.add_argument(
        "--device", default="auto",
        help="'auto' (default): require a CUDA GPU for the real backend and fail immediately if "
        "none is available - never silently falls back to CPU. 'cuda': same, explicit. 'cpu': "
        "explicit opt-out (e.g. local debugging of the real backend). Does not affect "
        "--backend smoke-test, which always runs on CPU regardless of this flag.",
    )
    return parser


def _resolve_device(device_arg: str) -> str:
    """Resolves --device for the *real* training backend only. 'auto'
    (the default) requires a CUDA-capable GPU and fails immediately,
    with a clear error, if none is available - this is what stops a
    real Kaggle GPU dispatch from silently training on CPU (the most
    severe gap found in the pre-first-real-run production audit: this
    flag previously defaulted to 'cpu' and kaggle_kernel_runner.py never
    overrode it). Pass --device cpu explicitly to opt out on purpose."""
    if device_arg == "cpu":
        return "cpu"
    try:
        import torch
    except ImportError as exc:
        raise RuntimeError(
            "--device auto/cuda requires torch to be installed (training[gpu-training] extra) "
            "to check CUDA availability"
        ) from exc
    if device_arg in ("auto", "cuda"):
        if not torch.cuda.is_available():
            raise RuntimeError(
                f"--device {device_arg} requires a CUDA-capable GPU, but torch.cuda.is_available() "
                "is False in this environment - refusing to silently fall back to CPU for a real "
                "training run. Pass --device cpu explicitly if you really want the real backend on CPU."
            )
        return "cuda"
    return device_arg  # e.g. an explicit "cuda:0", left as-is for advanced use


def _build_backend(args: argparse.Namespace, base_model_id: str, learning_rate: float, seed: int):
    if args.backend == "unavailable":
        return UnavailableWan22Backend()

    if args.backend in ("auto", "real"):
        manifest = resolve_local_weights(base_model_id, cache_root=args.models_cache_root)
        if manifest is not None:
            manifest.verify()
            registry_entries = load_wan22_registry_entries(args.registry)
            entry = registry_entries.get(base_model_id)
            if entry is None:
                raise ValueError(f"No Wan2.2 registry entry for base_model_id={base_model_id!r} in {args.registry}")
            from training import build_real_backend

            model_sources = {
                expert: Wan22ModelSource(pretrained_model_name_or_path=manifest.local_dir, subfolder=subfolder)
                for expert, subfolder in entry.experts.items()
            }
            return build_real_backend(
                base_model_id=base_model_id, model_sources=model_sources, device=_resolve_device(args.device),
                learning_rate=learning_rate, seed=seed,
            )
        if args.backend == "real":
            raise ValueError(
                f"--backend real requested but no verified weights are cached for {base_model_id!r} - run "
                "services/training/scripts/download_wan22_weights.py first"
            )

    if args.backend in ("auto", "smoke-test"):
        from training import build_smoke_test_backend

        return build_smoke_test_backend(base_model_id=base_model_id, learning_rate=learning_rate, seed=seed)

    raise ValueError(f"Unhandled --backend value: {args.backend!r}")


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
    try:
        backend = _build_backend(args, config.base_model_id, config.learning_rate, config.seed)
    except Exception as exc:  # noqa: BLE001 - real backend-selection failure, surfaced clearly
        print(f"[{args.job_id}] could not build a training backend: {exc}", file=sys.stderr)
        return 1
    print(f"[{args.job_id}] using backend: {type(backend).__name__}")

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
