"""Tests for services/training/entrypoints/kaggle_kernel_runner.py - the
real fix for dispatch_via_kaggle() pushing a kernel that couldn't
actually receive its config/manifest or run (see
docs/adr/0025-kaggle-dispatch-argv-fix.md). Runs the wrapper's real
subprocess-orchestration logic with `clone=False` pointed at this
checked-out repo (so no git clone or network access to GitHub happens),
using the real `download_wan22_weights.py` and `wan22_lora_train.py`
scripts - only the Hugging Face network call inside the download step
is out of this test's control, and its real (expected) failure in an
environment with no HF access is exactly what's asserted on.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest
from training import LoRAConfig, TrainingConfig

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "services" / "training" / "entrypoints" / "kaggle_kernel_runner.py"
_REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_module():
    spec = importlib.util.spec_from_file_location("kaggle_kernel_runner_under_test", _SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_input_dataset(tmp_path: Path) -> Path:
    input_root = tmp_path / "kaggle_input"
    dataset_dir = input_root / "job-input"
    dataset_dir.mkdir(parents=True)

    config = TrainingConfig(
        schema_version="1.0", run_id="kernel-runner-test", base_model_id="wan2.2-ti2v-5b",
        base_model_revision="2.2.0", strategy="lora", dataset_version="test", resolution="64x64", fps=8,
        max_frames=9, learning_rate=1e-4, batch_size=1, gradient_accumulation_steps=1, max_train_steps=4,
        mixed_precision="no", min_vram_gb=1.0, gpu_count=1, checkpoint_every_steps=2, eval_every_steps=2,
        seed=0, lora=LoRAConfig(rank=4, alpha=8, target_modules=("to_q", "to_k", "to_v", "to_out.0")),
    )
    config.to_yaml(dataset_dir / "config.yaml")
    (dataset_dir / "dataset_manifest.jsonl").write_text(
        json.dumps({"clip_id": "c1", "video_path": "/fake.mp4", "caption": "x", "width": 64, "height": 64,
                    "num_frames": 9, "fps": 8.0})
        + "\n"
    )
    return input_root


class TestKaggleKernelRunner:
    def test_raises_when_no_kaggle_input_dataset_mounted(self, tmp_path):
        module = _load_module()
        empty_input_root = tmp_path / "kaggle_input"
        empty_input_root.mkdir()

        with pytest.raises(RuntimeError, match="No dataset mounted"):
            module.main(
                repo_dir=_REPO_ROOT, kaggle_input_root=empty_input_root,
                kaggle_working_root=tmp_path / "kaggle_working", clone=False,
            )

    def test_fails_at_the_real_download_step_without_hf_network_access(self, tmp_path):
        # This sandbox's network egress to huggingface.co is blocked, so
        # the real download_wan22_weights.py subprocess this wrapper
        # shells out to is expected to fail here - proving the wrapper
        # gets there for real (clones skipped, no fabricated success),
        # not that the download itself succeeds. In an environment with
        # real HF access this same call would proceed to the training step.
        module = _load_module()
        input_root = _write_input_dataset(tmp_path)

        with pytest.raises(subprocess.CalledProcessError) as exc_info:
            module.main(
                repo_dir=_REPO_ROOT, kaggle_input_root=input_root,
                kaggle_working_root=tmp_path / "kaggle_working", clone=False,
            )

        assert "download_wan22_weights.py" in " ".join(exc_info.value.cmd)
