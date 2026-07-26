"""Phase 9 Preparation: the training framework core - config system
(TrainingConfig/LoRAConfig), checkpoint store, and the dry-run trainer.
Everything here is real, CPU-only logic: no GPU, no model download, no
training execution - see docs/adr/0021-phase9-preparation.md.
"""

from __future__ import annotations

import pytest
from training import (
    BASE_MODEL_REGISTRY,
    CheckpointRecord,
    DryRunTrainer,
    FilesystemCheckpointStore,
    InMemoryCheckpointStore,
    LoRAConfig,
    LoRAMergePlan,
    TrainingConfig,
)


def _valid_lora() -> LoRAConfig:
    return LoRAConfig(rank=16, alpha=32, target_modules=("to_q", "to_k"), dropout=0.1)


def _valid_config(**overrides) -> TrainingConfig:
    base = dict(
        schema_version="1.0",
        run_id="test-run",
        base_model_id="wan2.1",
        base_model_revision="2.1.0",
        strategy="lora",
        dataset_version="ds_abc123",
        resolution="1280x720",
        fps=24,
        max_frames=120,
        learning_rate=1e-4,
        batch_size=1,
        gradient_accumulation_steps=4,
        max_train_steps=10,
        mixed_precision="bf16",
        min_vram_gb=24.0,
        gpu_count=1,
        checkpoint_every_steps=3,
        eval_every_steps=3,
        seed=42,
        lora=_valid_lora(),
    )
    base.update(overrides)
    return TrainingConfig(**base)


# --- LoRAConfig -------------------------------------------------------


def test_lora_config_validate_accepts_sane_values():
    _valid_lora().validate()


@pytest.mark.parametrize(
    "overrides",
    [
        {"rank": 0},
        {"alpha": 0},
        {"target_modules": ()},
        {"dropout": 1.0},
        {"dropout": -0.1},
    ],
)
def test_lora_config_validate_rejects_bad_values(overrides):
    base_kwargs = {"rank": 16, "alpha": 32, "target_modules": ("to_q",), "dropout": 0.0}
    base_kwargs.update(overrides)
    with pytest.raises(ValueError):
        LoRAConfig(**base_kwargs).validate()


def test_lora_config_round_trips_through_dict():
    config = _valid_lora()
    restored = LoRAConfig.from_dict(config.to_dict())
    assert restored == config


def test_lora_merge_plan_validates_matching_lengths_and_nonnegative_weights():
    LoRAMergePlan(adapter_checkpoint_ids=("a", "b"), weights=(0.5, 0.5), target_checkpoint_id="merged").validate()

    with pytest.raises(ValueError):
        LoRAMergePlan(adapter_checkpoint_ids=("a", "b"), weights=(1.0,), target_checkpoint_id="merged").validate()
    with pytest.raises(ValueError):
        LoRAMergePlan(adapter_checkpoint_ids=("a",), weights=(-1.0,), target_checkpoint_id="merged").validate()
    with pytest.raises(ValueError):
        LoRAMergePlan(adapter_checkpoint_ids=(), weights=(), target_checkpoint_id="merged").validate()
    with pytest.raises(ValueError):
        LoRAMergePlan(adapter_checkpoint_ids=("a",), weights=(1.0,), target_checkpoint_id="").validate()


# --- TrainingConfig -----------------------------------------------------


def test_training_config_validate_accepts_sane_config():
    _valid_config().validate()


def test_training_config_requires_lora_when_strategy_is_lora():
    config = _valid_config(lora=None)
    with pytest.raises(ValueError):
        config.validate()


def test_training_config_full_finetune_does_not_require_lora():
    config = _valid_config(strategy="full_finetune", lora=None)
    config.validate()


@pytest.mark.parametrize(
    "overrides",
    [
        {"strategy": "not-a-strategy"},
        {"resolution": "not-a-resolution"},
        {"resolution": "abcxdef"},
        {"fps": 0},
        {"max_frames": 0},
        {"learning_rate": 0},
        {"batch_size": 0},
        {"gradient_accumulation_steps": 0},
        {"max_train_steps": 0},
        {"mixed_precision": "fp64"},
        {"min_vram_gb": 0},
        {"gpu_count": 0},
        {"checkpoint_every_steps": 0},
        {"eval_every_steps": 0},
    ],
)
def test_training_config_validate_rejects_bad_values(overrides):
    config = _valid_config(**overrides)
    with pytest.raises(ValueError):
        config.validate()


def test_training_config_round_trips_through_yaml(tmp_path):
    config = _valid_config()
    path = tmp_path / "config.yaml"
    config.to_yaml(path)

    restored = TrainingConfig.from_yaml(path)
    assert restored == config
    restored.validate()


def test_training_config_without_lora_round_trips_through_yaml(tmp_path):
    config = _valid_config(strategy="full_finetune", lora=None)
    path = tmp_path / "config.yaml"
    config.to_yaml(path)

    restored = TrainingConfig.from_yaml(path)
    assert restored.lora is None


def test_base_model_registry_has_all_required_base_models():
    # The original four Phase 9 Preparation candidates, plus the three
    # Wan2.2 variants added when Wan2.2 was selected as the foundation
    # model (docs/adr/0023-wan22-training-execution-layer.md).
    assert set(BASE_MODEL_REGISTRY) == {
        "wan2.1",
        "hunyuanvideo",
        "cogvideox",
        "stable-video-diffusion",
        "wan2.2-ti2v-5b",
        "wan2.2-t2v-a14b",
        "wan2.2-i2v-a14b",
    }
    for model_id, info in BASE_MODEL_REGISTRY.items():
        assert info.model_id == model_id
        assert info.display_name
        assert info.publisher
        assert info.license
        assert info.license_notes
        assert info.min_vram_gb > 0
        assert info.source_url.startswith("http")


def test_base_model_registry_wan21_is_fully_permissive_and_matches_existing_adapter():
    """Wan2.1 is this project's own existing incumbent engine
    (Wan21Adapter) - its license here must match what's already recorded
    on that adapter's CapabilityManifest (Apache-2.0), not drift."""
    info = BASE_MODEL_REGISTRY["wan2.1"]
    assert info.license == "Apache-2.0"
    assert info.commercial_use_verified is True


def test_base_model_registry_flags_non_trivial_licenses_as_unverified_for_commercial_use():
    """CogVideoX-5B and Stable Video Diffusion both have real
    commercial-use caveats (custom license / revenue threshold) - this
    must not be silently marked as verified."""
    assert BASE_MODEL_REGISTRY["cogvideox"].commercial_use_verified is False
    assert BASE_MODEL_REGISTRY["stable-video-diffusion"].commercial_use_verified is False


# --- CheckpointRecord / ICheckpointStore --------------------------------


def _checkpoint(checkpoint_id: str = "ckpt_1", run_id: str = "run_1", step: int = 100) -> CheckpointRecord:
    return CheckpointRecord(
        checkpoint_id=checkpoint_id,
        run_id=run_id,
        step=step,
        artifact_uri=f"dryrun://{run_id}/{checkpoint_id}",
        size_bytes=0,
        metrics={"loss": 0.5},
    )


def test_checkpoint_record_round_trips_through_dict():
    record = _checkpoint()
    restored = CheckpointRecord.from_dict(record.to_dict())
    assert restored == record


def test_in_memory_checkpoint_store_save_get_list_delete():
    store = InMemoryCheckpointStore()
    store.save(_checkpoint("ckpt_1", "run_1", 100))
    store.save(_checkpoint("ckpt_2", "run_1", 200))
    store.save(_checkpoint("ckpt_3", "run_2", 50))

    assert store.get("ckpt_1") is not None
    assert store.get("does-not-exist") is None

    run_1_checkpoints = store.list_for_run("run_1")
    assert [c.checkpoint_id for c in run_1_checkpoints] == ["ckpt_1", "ckpt_2"]  # sorted by step

    store.delete("ckpt_1")
    assert store.get("ckpt_1") is None


def test_filesystem_checkpoint_store_persists_across_instances(tmp_path):
    store = FilesystemCheckpointStore(tmp_path)
    store.save(_checkpoint("ckpt_1", "run_1", 100))

    reopened = FilesystemCheckpointStore(tmp_path)
    restored = reopened.get("ckpt_1")
    assert restored is not None
    assert restored.step == 100
    assert restored.metrics == {"loss": 0.5}


def test_filesystem_checkpoint_store_list_for_run_and_purge(tmp_path):
    store = FilesystemCheckpointStore(tmp_path)
    store.save(_checkpoint("ckpt_1", "run_1", 100))
    store.save(_checkpoint("ckpt_2", "run_1", 50))
    store.save(_checkpoint("ckpt_3", "run_2", 10))

    run_1 = store.list_for_run("run_1")
    assert [c.step for c in run_1] == [50, 100]  # sorted by step ascending

    store.purge_run("run_1")
    assert store.list_for_run("run_1") == []
    assert store.list_for_run("run_2") != []


# --- ITrainer / DryRunTrainer --------------------------------------------


def test_dry_run_trainer_produces_expected_checkpoint_cadence():
    store = InMemoryCheckpointStore()
    trainer = DryRunTrainer(store)
    config = _valid_config(max_train_steps=10, checkpoint_every_steps=3)

    result = trainer.train(config)

    assert result.status == "completed"
    assert result.final_step == 10
    # checkpoints at steps 3, 6, 9, and a final one at step 10 (max_train_steps,
    # even though it's not an exact multiple of checkpoint_every_steps).
    saved = store.list_for_run(config.run_id)
    assert [c.step for c in saved] == [3, 6, 9, 10]
    assert result.checkpoint_ids == [c.checkpoint_id for c in saved]


def test_dry_run_trainer_loss_metric_decreases_over_steps():
    store = InMemoryCheckpointStore()
    trainer = DryRunTrainer(store)
    config = _valid_config(max_train_steps=10, checkpoint_every_steps=5)

    trainer.train(config)

    checkpoints = store.list_for_run(config.run_id)
    losses = [c.metrics["loss"] for c in checkpoints]
    assert losses == sorted(losses, reverse=True)  # monotonically non-increasing


def test_dry_run_trainer_invokes_on_step_callback_every_step():
    seen_steps: list[int] = []
    trainer = DryRunTrainer(InMemoryCheckpointStore(), on_step=seen_steps.append)
    config = _valid_config(max_train_steps=7, checkpoint_every_steps=100)

    trainer.train(config)

    assert seen_steps == list(range(1, 8))


def test_dry_run_trainer_rejects_invalid_config_before_running():
    trainer = DryRunTrainer(InMemoryCheckpointStore())
    with pytest.raises(ValueError):
        trainer.train(_valid_config(max_train_steps=0))


def test_dry_run_trainer_reports_failed_status_when_a_step_raises():
    def _blow_up_on_step_4(step: int) -> None:
        if step == 4:
            raise RuntimeError("simulated mid-run failure")

    trainer = DryRunTrainer(InMemoryCheckpointStore(), on_step=_blow_up_on_step_4)
    config = _valid_config(max_train_steps=10, checkpoint_every_steps=2)

    result = trainer.train(config)

    assert result.status == "failed"
    assert result.final_step == 4  # step is incremented before on_step() fires, so this is where it stopped
    assert "simulated mid-run failure" in result.error_message
    assert result.checkpoint_ids == [f"ckpt_{config.run_id}_000002"]  # the one checkpoint before the failure
