"""Tests for infra/kaggle/kaggle_inference_kernel_runner.py's real-input
discovery fix. A real run (30279700088) showed the dataset dispatch_inference.py
attaches really was mounted, but Kaggle nested it one level deeper than
assumed (/kaggle/input/datasets/<slug>/ instead of /kaggle/input/<slug>/),
so a plain top-level glob("*") picked the "datasets" parent itself and
never found git_ref.txt/inference_request.json. These tests exercise only
the input-discovery logic (which runs before the CUDA check), so no torch
import or GPU is required.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "infra" / "kaggle" / "kaggle_inference_kernel_runner.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("kaggle_inference_kernel_runner_under_test", _SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_job_files(dataset_dir: Path) -> None:
    dataset_dir.mkdir(parents=True)
    (dataset_dir / "git_ref.txt").write_text("claude/sallehly-engine-audit-vnxs4f")
    (dataset_dir / "inference_request.json").write_text(
        json.dumps({"model_id": "Wan-AI/Wan2.2-TI2V-5B-Diffusers", "seed": 0, "job_input": {"prompt": "x"}})
    )


class TestKaggleInferenceKernelRunnerInputDiscovery:
    def test_raises_when_nothing_mounted(self, tmp_path):
        module = _load_module()
        empty_input_root = tmp_path / "kaggle_input"
        empty_input_root.mkdir()

        with pytest.raises(RuntimeError, match="No git_ref.txt found"):
            module.main(kaggle_input_root=empty_input_root, kaggle_working_root=tmp_path / "kaggle_working", clone=False)

    def test_finds_flat_layout(self, tmp_path, monkeypatch):
        # Older/simpler layout: /kaggle/input/<dataset-slug>/{git_ref.txt,inference_request.json}
        module = _load_module()
        input_root = tmp_path / "kaggle_input"
        _write_job_files(input_root / "wan-inference-123-input")
        monkeypatch.setattr(module, "_verify_cuda_available", lambda: (_ for _ in ()).throw(RuntimeError("stop-after-discovery")))

        with pytest.raises(RuntimeError, match="stop-after-discovery"):
            module.main(kaggle_input_root=input_root, kaggle_working_root=tmp_path / "kaggle_working", clone=False)

    def test_finds_nested_datasets_layout(self, tmp_path, monkeypatch):
        # Real layout observed on run 30279700088: Kaggle nested the
        # dataset one level deeper under a "datasets" parent directory.
        module = _load_module()
        input_root = tmp_path / "kaggle_input"
        _write_job_files(input_root / "datasets" / "wan-inference-123-input")
        monkeypatch.setattr(module, "_verify_cuda_available", lambda: (_ for _ in ()).throw(RuntimeError("stop-after-discovery")))

        with pytest.raises(RuntimeError, match="stop-after-discovery"):
            module.main(kaggle_input_root=input_root, kaggle_working_root=tmp_path / "kaggle_working", clone=False)

    def test_raises_when_request_json_missing(self, tmp_path):
        module = _load_module()
        input_root = tmp_path / "kaggle_input"
        dataset_dir = input_root / "wan-inference-123-input"
        dataset_dir.mkdir(parents=True)
        (dataset_dir / "git_ref.txt").write_text("main")

        with pytest.raises(RuntimeError, match="inference_request.json"):
            module.main(kaggle_input_root=input_root, kaggle_working_root=tmp_path / "kaggle_working", clone=False)
