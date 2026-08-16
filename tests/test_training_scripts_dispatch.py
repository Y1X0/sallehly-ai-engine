"""Tests for services/training/scripts/run_experiment.py's --dispatch
wiring (docs/adr/0024-wan22-real-training-backend.md decision 8) - real
KaggleClient/ModalJobLauncher are replaced with injected fakes (same
`runner=`-injection pattern the automation layer's own tests already
use), so no network access or real Kaggle/Modal CLI is touched here.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

from training import LoRAConfig, TrainingConfig

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "services" / "training" / "scripts" / "run_experiment.py"


def _load_run_experiment_module():
    spec = importlib.util.spec_from_file_location("run_experiment_under_test", _SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fake_result(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


def _write_base_config(tmp_path: Path) -> Path:
    config = TrainingConfig(
        schema_version="1.0", run_id="base-run", base_model_id="wan2.2-ti2v-5b", base_model_revision="2.2.0",
        strategy="lora", dataset_version="test", resolution="64x64", fps=8, max_frames=9, learning_rate=1e-4,
        batch_size=1, gradient_accumulation_steps=1, max_train_steps=100, mixed_precision="no", min_vram_gb=1.0,
        gpu_count=1, checkpoint_every_steps=10, eval_every_steps=10, seed=0,
        lora=LoRAConfig(rank=4, alpha=8, target_modules=("to_q", "to_k", "to_v", "to_out.0")),
    )
    path = tmp_path / "base_config.yaml"
    config.to_yaml(path)
    return path


def _write_allowed_ranges(tmp_path: Path) -> Path:
    path = tmp_path / "allowed_ranges.json"
    path.write_text(json.dumps({"learning_rate": [1e-6, 5e-4], "max_train_steps": [10, 2000]}))
    return path


def _write_manifest(tmp_path: Path) -> Path:
    path = tmp_path / "manifest.jsonl"
    path.write_text(
        json.dumps(
            {"clip_id": "c1", "video_path": "/fake.mp4", "caption": "x", "width": 64, "height": 64,
             "num_frames": 9, "fps": 8.0}
        )
        + "\n"
    )
    return path


class TestDispatchWiring:
    def test_dispatch_requires_dataset_manifest(self, tmp_path):
        module = _load_run_experiment_module()
        base_config = _write_base_config(tmp_path)
        allowed_ranges = _write_allowed_ranges(tmp_path)

        exit_code = module.main([
            "--base-config", str(base_config), "--allowed-ranges", str(allowed_ranges),
            "--tier", "free_gpu", "--provider", "kaggle", "--dispatch",
            "--job-store-dir", str(tmp_path / "jobs"),
        ])

        assert exit_code == 1

    def test_dispatch_rejects_unsupported_provider(self, tmp_path):
        module = _load_run_experiment_module()
        base_config = _write_base_config(tmp_path)
        allowed_ranges = _write_allowed_ranges(tmp_path)
        manifest = _write_manifest(tmp_path)

        exit_code = module.main([
            "--base-config", str(base_config), "--allowed-ranges", str(allowed_ranges),
            "--tier", "free_gpu", "--provider", "fal", "--dispatch",
            "--dataset-manifest", str(manifest), "--job-store-dir", str(tmp_path / "jobs"),
        ])

        assert exit_code == 1

    def test_dispatch_via_kaggle_calls_real_client_with_injected_runner(self, tmp_path, monkeypatch):
        module = _load_run_experiment_module()
        base_config = _write_base_config(tmp_path)
        allowed_ranges = _write_allowed_ranges(tmp_path)
        manifest = _write_manifest(tmp_path)

        calls: list[list[str]] = []

        def fake_runner(args: list[str]) -> subprocess.CompletedProcess:
            calls.append(args)
            return _fake_result(stdout="OK")

        real_kaggle_client_cls = module.KaggleClient
        monkeypatch.setattr(module, "KaggleClient", lambda: real_kaggle_client_cls(runner=fake_runner))
        # dispatch_via_kaggle() waits _DATASET_PROCESSING_DELAY_SECONDS (real
        # seconds) between the dataset upload and the kernel push - this CLI
        # path has no way to inject a fake sleep_fn, so patch time.sleep
        # itself (resolved at call time, not a bound default - see
        # dispatch.py's own comment) to keep this test fast.
        from training.wan22 import dispatch as dispatch_module
        monkeypatch.setattr(dispatch_module.time, "sleep", lambda _s: None)
        fake_entrypoint = tmp_path / "entrypoint_dir" / "wan22_lora_train.py"
        fake_entrypoint.parent.mkdir(parents=True)
        fake_entrypoint.write_text("# fake entrypoint for this test\n")

        exit_code = module.main([
            "--base-config", str(base_config), "--allowed-ranges", str(allowed_ranges),
            "--tier", "free_gpu", "--provider", "kaggle", "--dispatch",
            "--dataset-manifest", str(manifest), "--job-store-dir", str(tmp_path / "jobs"),
            "--dispatch-runs-dir", str(tmp_path / "runs"), "--kaggle-kernel-ref", "me/my-kernel",
            "--entrypoint", str(fake_entrypoint),
        ])

        assert exit_code == 0
        assert any("kernels" in call and "push" in call for call in calls)
        # the copied manifest + written config must actually exist on disk
        run_dirs = list((tmp_path / "runs").iterdir())
        assert len(run_dirs) == 1
        assert (run_dirs[0] / "dataset_manifest.jsonl").is_file()
        assert (run_dirs[0] / "config.yaml").is_file()
        # dispatch_via_kaggle writes kernel-metadata.json next to the
        # entrypoint - must land in the isolated tmp dir, never the repo
        assert (fake_entrypoint.parent / "kernel-metadata.json").is_file()

    def test_dispatch_via_modal_calls_real_launcher_with_injected_runner(self, tmp_path, monkeypatch):
        module = _load_run_experiment_module()
        base_config = _write_base_config(tmp_path)
        allowed_ranges = _write_allowed_ranges(tmp_path)
        manifest = _write_manifest(tmp_path)

        calls: list[list[str]] = []

        def fake_runner(args: list[str]) -> subprocess.CompletedProcess:
            calls.append(args)
            return _fake_result(stdout="Created app ap-abc123")

        real_modal_launcher_cls = module.ModalJobLauncher
        monkeypatch.setattr(module, "ModalJobLauncher", lambda: real_modal_launcher_cls(runner=fake_runner))

        exit_code = module.main([
            "--base-config", str(base_config), "--allowed-ranges", str(allowed_ranges),
            "--tier", "free_gpu", "--provider", "modal", "--dispatch",
            "--dataset-manifest", str(manifest), "--job-store-dir", str(tmp_path / "jobs"),
            "--dispatch-runs-dir", str(tmp_path / "runs"),
        ])

        assert exit_code == 0
        assert any("run" in call and "--detach" in call for call in calls)

    def test_dispatch_failure_marks_job_failed(self, tmp_path, monkeypatch):
        module = _load_run_experiment_module()
        base_config = _write_base_config(tmp_path)
        allowed_ranges = _write_allowed_ranges(tmp_path)
        manifest = _write_manifest(tmp_path)
        fake_entrypoint = tmp_path / "entrypoint_dir" / "wan22_lora_train.py"
        fake_entrypoint.parent.mkdir(parents=True)
        fake_entrypoint.write_text("# fake entrypoint for this test\n")

        def failing_runner(args: list[str]) -> subprocess.CompletedProcess:
            return _fake_result(returncode=1)

        real_kaggle_client_cls = module.KaggleClient
        monkeypatch.setattr(module, "KaggleClient", lambda: real_kaggle_client_cls(runner=failing_runner))

        exit_code = module.main([
            "--base-config", str(base_config), "--allowed-ranges", str(allowed_ranges),
            "--tier", "free_gpu", "--provider", "kaggle", "--dispatch",
            "--dataset-manifest", str(manifest), "--job-store-dir", str(tmp_path / "jobs"),
            "--dispatch-runs-dir", str(tmp_path / "runs"), "--kaggle-kernel-ref", "me/my-kernel",
            "--job-id", "job-fixed-id", "--entrypoint", str(fake_entrypoint),
        ])

        assert exit_code == 1
        job = module.FilesystemJobStatusStore(tmp_path / "jobs").get("job-fixed-id")
        assert job.status.value == "failed"
        assert "kaggle CLI command failed" in job.error_message
