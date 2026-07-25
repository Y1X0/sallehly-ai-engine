"""Phase 9 Preparation: the four prepared base-model training configs
(services/training/configs/) actually load, validate, and reference a
real entry in BASE_MODEL_REGISTRY - real config-file correctness, not
just that the Python objects work in isolation. See
docs/adr/0021-phase9-preparation.md.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from training import BASE_MODEL_REGISTRY, TrainingConfig

_CONFIGS_DIR = Path(__file__).resolve().parent.parent / "services" / "training" / "configs"

_EXPECTED_FILES = {
    "wan21_finetune.yaml": "wan2.1",
    "hunyuanvideo_finetune.yaml": "hunyuanvideo",
    "cogvideox_finetune.yaml": "cogvideox",
    "stable_video_diffusion_finetune.yaml": "stable-video-diffusion",
}


def test_all_four_expected_config_files_exist():
    for filename in _EXPECTED_FILES:
        assert (_CONFIGS_DIR / filename).is_file(), f"missing {filename}"


@pytest.mark.parametrize("filename,expected_base_model_id", list(_EXPECTED_FILES.items()))
def test_config_loads_validates_and_matches_its_base_model(filename, expected_base_model_id):
    config = TrainingConfig.from_yaml(_CONFIGS_DIR / filename)
    config.validate()

    assert config.base_model_id == expected_base_model_id
    assert config.base_model_id in BASE_MODEL_REGISTRY
    assert config.strategy == "lora"
    assert config.lora is not None
    config.lora.validate()

    base_info = BASE_MODEL_REGISTRY[config.base_model_id]
    assert config.min_vram_gb >= base_info.min_vram_gb - 1e-6


def test_wan21_config_reuses_this_projects_own_existing_engine_defaults():
    """Wan2.1 is the one base model this repo already runs against
    (Wan21Adapter's CapabilityManifest) - its config's resolution/fps
    must not silently diverge from what that adapter already declares."""
    config = TrainingConfig.from_yaml(_CONFIGS_DIR / "wan21_finetune.yaml")
    assert config.resolution == "1280x720"
    assert config.fps == 24


def test_every_config_run_id_is_unique():
    run_ids = [TrainingConfig.from_yaml(_CONFIGS_DIR / f).run_id for f in _EXPECTED_FILES]
    assert len(run_ids) == len(set(run_ids))


def test_svd_config_notes_its_image_conditioned_pipeline_difference():
    """Stable Video Diffusion is image-conditioned, not text-to-video -
    the config's own notes must say so, since silently treating it like
    the other three (pure text-to-video) configs would be a real data
    pipeline mistake at training time."""
    config = TrainingConfig.from_yaml(_CONFIGS_DIR / "stable_video_diffusion_finetune.yaml")
    assert "image" in config.notes.lower()
