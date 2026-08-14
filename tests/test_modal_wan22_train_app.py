"""Tests for services/training/entrypoints/modal_wan22_train_app.py -
the Modal-provider equivalent of kaggle_kernel_runner.py, built after
real evidence (infra/kaggle/kaggle_disk_diagnostic_kernel.py) that
Kaggle's free-tier disk (~19.5GB) cannot hold Wan2.2-TI2V-5B's real
weight footprint (~31.85GB).

Verifies two independent things, both without any real Modal account,
GPU, or network access:
  1. The real `modal.App`/`modal.Volume`/`modal.Image`/`@app.function`
     objects construct correctly against a real, locally-installed
     `modal` package (skipped entirely if `modal` isn't installed -
     run with `uv run --with modal pytest tests/test_modal_wan22_train_app.py`).
  2. `_run_training`'s real sequencing logic (weight-cache check, then
     invoke the existing wan22_lora_train.py --backend real
     unmodified) is correct, via an injected fake `run` callable - the
     same pattern tests/test_training_kaggle_kernel_runner.py already
     uses for kaggle_kernel_runner.main().
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

modal = pytest.importorskip("modal")

_SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "services" / "training" / "entrypoints" / "modal_wan22_train_app.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("modal_wan22_train_app_under_test", _SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestModalAppConstruction:
    def test_app_volume_and_function_construct_against_the_real_modal_sdk(self):
        module = _load_module()

        assert isinstance(module.app, modal.App)
        assert isinstance(module.volume, modal.Volume)
        assert module.train_wan22_lora is not None

    def test_train_wan22_lora_requests_a10g_not_a100(self):
        # Explicit user requirement: A10G for this first probe, not A100 -
        # verified against the function's own real, hydrated Modal spec,
        # not just the module-level constant.
        module = _load_module()
        assert module.train_wan22_lora.spec.gpus == "A10G"

    def test_train_wan22_lora_mounts_the_persistent_volume(self):
        module = _load_module()
        assert module._VOLUME_MOUNT_PATH in module.train_wan22_lora.spec.volumes
        mounted = module.train_wan22_lora.spec.volumes[module._VOLUME_MOUNT_PATH]
        assert mounted.name == module.volume.name == module._VOLUME_NAME


class TestWeightsAlreadyCached:
    def test_false_when_no_engine_dir_exists(self, tmp_path):
        module = _load_module()
        assert module._weights_already_cached(tmp_path) is False

    def test_false_when_engine_dir_exists_but_has_no_safetensors(self, tmp_path):
        module = _load_module()
        engine_dir = tmp_path / module._ENGINE_ID
        engine_dir.mkdir()
        (engine_dir / "config.json").write_text("{}")
        assert module._weights_already_cached(tmp_path) is False

    def test_true_once_a_real_safetensors_shard_is_present(self, tmp_path):
        module = _load_module()
        engine_dir = tmp_path / module._ENGINE_ID / "transformer"
        engine_dir.mkdir(parents=True)
        (engine_dir / "diffusion_pytorch_model-00001-of-00005.safetensors").write_bytes(b"\x00")
        assert module._weights_already_cached(tmp_path) is True


class TestRunTraining:
    def test_downloads_weights_then_trains_when_nothing_cached(self, tmp_path):
        module = _load_module()
        calls: list[tuple[list[str], Path | None]] = []

        exit_code = module._run_training(
            config_path="/vol/runs/job-1/config.yaml",
            dataset_manifest_path="/vol/runs/job-1/dataset_manifest.jsonl",
            output_dir="/vol/runs/job-1/output",
            checkpoint_store_dir="/vol/runs/job-1/checkpoints",
            job_id="job-1",
            repo_root=tmp_path / "repo",
            models_cache_root=tmp_path / "models-cache",
            run=lambda args, cwd=None: calls.append((args, cwd)),
        )

        assert exit_code == 0
        assert len(calls) == 2
        download_args, download_cwd = calls[0]
        assert "download_wan22_weights.py" in " ".join(download_args)
        assert "--engine-id" in download_args
        assert module._ENGINE_ID in download_args
        assert download_cwd == tmp_path / "repo"

        train_args, train_cwd = calls[1]
        assert "wan22_lora_train.py" in " ".join(train_args)
        assert "--config" in train_args
        assert train_args[train_args.index("--config") + 1] == "/vol/runs/job-1/config.yaml"
        assert "--dataset-manifest" in train_args
        assert train_args[train_args.index("--dataset-manifest") + 1] == "/vol/runs/job-1/dataset_manifest.jsonl"
        assert "--job-id" in train_args
        assert train_args[train_args.index("--job-id") + 1] == "job-1"
        assert "--backend" in train_args
        assert train_args[train_args.index("--backend") + 1] == "real"
        assert "--device" in train_args
        assert train_args[train_args.index("--device") + 1] == "auto"
        assert train_cwd == tmp_path / "repo"

    def test_skips_the_real_download_when_weights_already_cached_on_the_volume(self, tmp_path):
        # The real point of the Volume: a second run must not re-pay the
        # real ~31.85GB transfer.
        module = _load_module()
        models_cache_root = tmp_path / "models-cache"
        engine_dir = models_cache_root / module._ENGINE_ID / "transformer"
        engine_dir.mkdir(parents=True)
        (engine_dir / "diffusion_pytorch_model-00001-of-00005.safetensors").write_bytes(b"\x00")
        calls: list[list[str]] = []

        exit_code = module._run_training(
            config_path="/vol/runs/job-2/config.yaml",
            dataset_manifest_path="/vol/runs/job-2/dataset_manifest.jsonl",
            output_dir="/vol/runs/job-2/output",
            checkpoint_store_dir="/vol/runs/job-2/checkpoints",
            job_id="job-2",
            repo_root=tmp_path / "repo",
            models_cache_root=models_cache_root,
            run=lambda args, cwd=None: calls.append(args),
        )

        assert exit_code == 0
        assert len(calls) == 1
        assert "wan22_lora_train.py" in " ".join(calls[0])
        assert not any("download_wan22_weights.py" in " ".join(c) for c in calls)
