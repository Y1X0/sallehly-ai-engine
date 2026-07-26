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

torch = pytest.importorskip("torch")

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "services" / "training" / "entrypoints" / "kaggle_kernel_runner.py"
_REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_module():
    spec = importlib.util.spec_from_file_location("kaggle_kernel_runner_under_test", _SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_input_dataset(tmp_path: Path, *, include_git_ref: bool = True) -> Path:
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
    if include_git_ref:
        (dataset_dir / "git_ref.txt").write_text("claude/sallehly-engine-audit-vnxs4f")
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

    def test_raises_when_no_cuda_available(self, tmp_path, monkeypatch):
        # The most severe gap the pre-first-real-run production audit
        # found: without this check, a misconfigured (no-GPU) Kaggle
        # kernel would silently reach the training step and train on
        # CPU. This sandbox itself has no GPU, but the check is forced
        # explicitly here so the test doesn't depend on that incidental
        # fact of the environment it happens to run in.
        module = _load_module()
        input_root = _write_input_dataset(tmp_path)
        monkeypatch.setattr(torch.cuda, "is_available", lambda: False)

        with pytest.raises(RuntimeError, match="CUDA"):
            module.main(
                repo_dir=_REPO_ROOT, kaggle_input_root=input_root,
                kaggle_working_root=tmp_path / "kaggle_working", clone=False,
            )

    def test_fails_at_the_real_download_step_without_hf_network_access(self, tmp_path, monkeypatch):
        # This sandbox's network egress to huggingface.co is blocked, so
        # the real download_wan22_weights.py subprocess this wrapper
        # shells out to is expected to fail here - proving the wrapper
        # gets there for real (clones skipped, no fabricated success),
        # not that the download itself succeeds. In an environment with
        # real HF access this same call would proceed to the training step.
        # CUDA availability is simulated True here (this sandbox has no
        # real GPU) purely so the test can reach past the CUDA check
        # exercised separately above.
        module = _load_module()
        input_root = _write_input_dataset(tmp_path)
        monkeypatch.setattr(torch.cuda, "is_available", lambda: True)

        with pytest.raises(subprocess.CalledProcessError) as exc_info:
            module.main(
                repo_dir=_REPO_ROOT, kaggle_input_root=input_root,
                kaggle_working_root=tmp_path / "kaggle_working", clone=False,
            )

        assert "download_wan22_weights.py" in " ".join(exc_info.value.cmd)

    def test_install_missing_packages_never_touches_torch(self, tmp_path, monkeypatch):
        # Core of the fix: pip must never be asked to resolve `torch` at
        # all here, since that risks replacing Kaggle's preinstalled
        # CUDA-enabled build with an unrelated one from PyPI.
        module = _load_module()
        calls: list[list[str]] = []
        monkeypatch.setattr(module.subprocess, "run", lambda args, check=True: calls.append(args))
        monkeypatch.setattr(module.importlib.util, "find_spec", lambda name: None)  # everything "missing"

        module._install_missing_packages(tmp_path / "repo")

        assert len(calls) == 2
        for call in calls:
            assert "--no-deps" in call
            assert not any("torch" in arg.lower() for arg in call)

    def test_wan22_lora_train_invocation_passes_device_auto(self, tmp_path, monkeypatch):
        # Fix #1's other half: the wrapper must explicitly pass --device
        # auto so wan22_lora_train.py's own CUDA fail-fast is in force,
        # rather than relying on a default that could silently change.
        module = _load_module()
        input_root = _write_input_dataset(tmp_path)
        monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
        calls: list[list[str]] = []
        monkeypatch.setattr(module, "_run", lambda args: calls.append(args))

        module.main(
            repo_dir=_REPO_ROOT, kaggle_input_root=input_root,
            kaggle_working_root=tmp_path / "kaggle_working", clone=False,
        )

        train_call = next(c for c in calls if "wan22_lora_train.py" in " ".join(c))
        assert "--device" in train_call
        assert train_call[train_call.index("--device") + 1] == "auto"

    def test_raises_when_git_ref_missing_from_older_dispatch(self, tmp_path):
        # Simulates a kernel pushed by a pre-ADR-0025-git-ref-fix
        # dispatch_via_kaggle() (config + manifest present, no
        # git_ref.txt) - must fail with a clear, specific message rather
        # than silently cloning the wrong branch.
        module = _load_module()
        input_root = _write_input_dataset(tmp_path, include_git_ref=False)

        with pytest.raises(RuntimeError, match="git_ref.txt"):
            module.main(
                repo_dir=_REPO_ROOT, kaggle_input_root=input_root,
                kaggle_working_root=tmp_path / "kaggle_working", clone=False,
            )
