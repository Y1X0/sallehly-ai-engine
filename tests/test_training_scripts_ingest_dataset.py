"""Tests for services/training/scripts/ingest_dataset.py - the real,
end-to-end DatasetManager pipeline wired into one CLI. Uses real ffmpeg-
generated synthetic clips (same convention as test_training_dataset.py/
media_helpers.py); skipped entirely when ffmpeg is not installed.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from media_helpers import FFMPEG_AVAILABLE, make_color_clip
from training import FilesystemDatasetVersionStore, TrainingConfig

pytestmark = pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed")

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "services" / "training" / "scripts" / "ingest_dataset.py"


def _load_ingest_module():
    spec = importlib.util.spec_from_file_location("ingest_dataset_under_test", _SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_clips_dir(tmp_path: Path, n: int = 3) -> Path:
    clips_dir = tmp_path / "clips"
    clips_dir.mkdir()
    for i, color in enumerate(["red", "green", "blue"][:n]):
        make_color_clip(clips_dir / f"clip_{i}.mp4", color, duration=1.0, size="320x240", rate=24)
    return clips_dir


class TestIngestDataset:
    def test_refuses_without_rights_cleared_flag(self, tmp_path, capsys):
        module = _load_ingest_module()
        clips_dir = _make_clips_dir(tmp_path)

        exit_code = module.main(["--clips-dir", str(clips_dir)])

        assert exit_code == 1
        assert "rights-cleared" in capsys.readouterr().err

    def test_ingests_and_versions_real_clips(self, tmp_path):
        module = _load_ingest_module()
        clips_dir = _make_clips_dir(tmp_path)

        exit_code = module.main([
            "--clips-dir", str(clips_dir), "--rights-cleared", "--tag", "smoke-test",
            "--version-store-dir", str(tmp_path / "versions"),
        ])

        assert exit_code == 0
        versions = FilesystemDatasetVersionStore(tmp_path / "versions").list_all()
        assert len(versions) == 1
        assert versions[0].statistics.clip_count == 3

    def test_writes_wan22_manifest_when_base_model_config_given(self, tmp_path):
        module = _load_ingest_module()
        clips_dir = _make_clips_dir(tmp_path, n=2)
        base_config_path = tmp_path / "base_config.yaml"
        from training import LoRAConfig

        config = TrainingConfig(
            schema_version="1.0", run_id="ingest-test", base_model_id="wan2.2-ti2v-5b", base_model_revision="2.2.0",
            strategy="lora", dataset_version="placeholder", resolution="320x240", fps=24, max_frames=24,
            learning_rate=1e-4, batch_size=1, gradient_accumulation_steps=1, max_train_steps=10,
            mixed_precision="no", min_vram_gb=1.0, gpu_count=1, checkpoint_every_steps=5, eval_every_steps=5,
            seed=0, lora=LoRAConfig(rank=4, alpha=8, target_modules=("to_q", "to_k", "to_v", "to_out.0")),
        )
        config.to_yaml(base_config_path)

        exit_code = module.main([
            "--clips-dir", str(clips_dir), "--rights-cleared", "--val-fraction", "0.0", "--test-fraction", "0.0",
            "--version-store-dir", str(tmp_path / "versions"), "--manifest-output-dir", str(tmp_path / "manifests"),
            "--base-model-config", str(base_config_path),
        ])

        assert exit_code == 0
        manifest_files = list((tmp_path / "manifests").glob("*_train.jsonl"))
        assert len(manifest_files) == 1
        entries = [json.loads(line) for line in manifest_files[0].read_text().splitlines()]
        assert len(entries) == 2
        assert all(e["caption"] for e in entries)

    def test_no_video_files_found_is_an_error(self, tmp_path):
        module = _load_ingest_module()
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        exit_code = module.main(["--clips-dir", str(empty_dir), "--rights-cleared"])

        assert exit_code == 1
