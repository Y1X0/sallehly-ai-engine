"""Tests for services/training/src/training/wan22/diffusers_backend.py -
the real IWan22TrainingBackend. Requires the training[gpu-training]
extra (torch/diffusers/peft); skipped entirely when it is not installed,
exactly like the ffmpeg-gated tests in test_training_dataset.py skip
when ffmpeg is absent. Runs a real (tiny-scale) forward/backward/
optimizer/checkpoint-save through the real diffusers WanTransformer3DModel
class and real peft LoRA injection - CPU-only, seconds, no GPU or real
Wan2.2 weights.
"""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("diffusers")
pytest.importorskip("peft")

from training import (  # noqa: E402
    FilesystemCheckpointStore,
    LoRAConfig,
    TrainingConfig,
    Wan22CheckpointWriter,
    Wan22LoRAConfig,
    Wan22LoRATrainer,
    Wan22ManifestEntry,
)
from training.wan22.diffusers_backend import (  # noqa: E402
    RandomLatentBatchEncoder,
    Wan22DiffusersBackend,
    Wan22ModelSource,
    build_smoke_test_backend,
    default_model_sources,
)


def _config(base_model_id: str, *, max_train_steps: int = 4, checkpoint_every: int = 2, seed: int = 0) -> TrainingConfig:
    config = TrainingConfig(
        schema_version="1.0", run_id=f"test-{base_model_id}", base_model_id=base_model_id,
        base_model_revision="2.2.0", strategy="lora", dataset_version="test", resolution="64x64", fps=8,
        max_frames=9, learning_rate=1e-3, batch_size=1, gradient_accumulation_steps=1,
        max_train_steps=max_train_steps, mixed_precision="no", min_vram_gb=1.0, gpu_count=1,
        checkpoint_every_steps=checkpoint_every, eval_every_steps=checkpoint_every, seed=seed,
        lora=LoRAConfig(rank=4, alpha=8, target_modules=("to_q", "to_k", "to_v", "to_out.0"), dropout=0.0),
    )
    config.validate()
    return config


def _entries(n: int = 2) -> list[Wan22ManifestEntry]:
    return [
        Wan22ManifestEntry(
            clip_id=f"clip_{i}", video_path=f"/fake/{i}.mp4", caption="a test clip",
            width=64, height=64, num_frames=9, fps=8.0,
        )
        for i in range(n)
    ]


class TestWan22ModelSource:
    def test_default_model_sources_unified(self):
        sources = default_model_sources("wan2.2-ti2v-5b", "some/repo")
        assert sources == {"unified": Wan22ModelSource("some/repo", subfolder="transformer")}

    def test_default_model_sources_moe(self):
        sources = default_model_sources("wan2.2-t2v-a14b", "some/repo")
        assert sources == {
            "high_noise": Wan22ModelSource("some/repo", subfolder="transformer"),
            "low_noise": Wan22ModelSource("some/repo", subfolder="transformer_2"),
        }


class TestWan22DiffusersBackendConstruction:
    def test_requires_either_smoke_test_or_model_sources(self):
        with pytest.raises(ValueError, match="model_sources is required"):
            Wan22DiffusersBackend(base_model_id="wan2.2-ti2v-5b")

    def test_rejects_both_smoke_test_and_model_sources(self):
        with pytest.raises(ValueError, match="not both"):
            Wan22DiffusersBackend(
                base_model_id="wan2.2-ti2v-5b", smoke_test=True,
                model_sources={"unified": Wan22ModelSource("a/b")},
            )


class TestRandomLatentBatchEncoder:
    def test_encode_shapes_derive_from_real_entry_metadata(self):
        encoder = RandomLatentBatchEncoder(seed=0, latent_channels=4, text_dim=32, text_seq_len=8)
        entry = Wan22ManifestEntry(
            clip_id="c1", video_path="/fake.mp4", caption="x", width=64, height=64, num_frames=9, fps=8.0,
        )

        hidden_states, encoder_hidden_states = encoder.encode(entry, device="cpu")

        assert hidden_states.shape == (1, 4, 3, 8, 8)  # (1,c,(9-1)//4+1,64/8,64/8)
        assert encoder_hidden_states.shape == (1, 8, 32)

    def test_encode_is_deterministic_for_same_clip_id(self):
        encoder = RandomLatentBatchEncoder(seed=42)
        entry = Wan22ManifestEntry(
            clip_id="stable-clip", video_path="/fake.mp4", caption="x", width=64, height=64, num_frames=9, fps=8.0,
        )

        first, _ = encoder.encode(entry, device="cpu")
        second, _ = encoder.encode(entry, device="cpu")

        assert torch.equal(first, second)


class TestWan22DiffusersBackendSmokeTest:
    def test_unified_model_trains_and_checkpoints_successfully(self, tmp_path):
        config = _config("wan2.2-ti2v-5b")
        lora_config = Wan22LoRAConfig.from_training_config(config)
        backend = build_smoke_test_backend(base_model_id=config.base_model_id, seed=config.seed)
        store = FilesystemCheckpointStore(tmp_path / "checkpoints")
        writer = Wan22CheckpointWriter(store)
        trainer = Wan22LoRATrainer(
            backend=backend, checkpoint_writer=writer, dataset_entries=_entries(), lora_config=lora_config,
            output_dir=tmp_path / "output",
        )

        result = trainer.train(config)

        assert result.status == "completed", result.error_message
        assert result.final_step == config.max_train_steps
        assert len(result.checkpoint_ids) == 2  # checkpoint_every_steps=2, max_train_steps=4
        for checkpoint_id in result.checkpoint_ids:
            record = store.get(checkpoint_id)
            assert record.artifact_uri.startswith("file://")
            assert (tmp_path / "output" / "adapters" / "unified" / f"step_{record.step:06d}").is_dir()

    def test_a14b_moe_model_trains_both_experts_and_pairs_checkpoints(self, tmp_path):
        config = _config("wan2.2-t2v-a14b", max_train_steps=2, checkpoint_every=2)
        lora_config = Wan22LoRAConfig.from_training_config(config)
        backend = build_smoke_test_backend(base_model_id=config.base_model_id, seed=config.seed)
        store = FilesystemCheckpointStore(tmp_path / "checkpoints")
        writer = Wan22CheckpointWriter(store)
        trainer = Wan22LoRATrainer(
            backend=backend, checkpoint_writer=writer, dataset_entries=_entries(1), lora_config=lora_config,
            output_dir=tmp_path / "output",
        )

        result = trainer.train(config)

        assert result.status == "completed", result.error_message
        assert len(result.checkpoint_ids) == 2  # one per expert
        paired = writer.get_paired_checkpoints(config.run_id, 2, frozenset(lora_config.experts))
        assert set(paired) == {"high_noise", "low_noise"}

    def test_loss_actually_changes_the_lora_weights(self, tmp_path):
        # Real gradient descent, not a no-op: run one step, save a
        # checkpoint, run more steps, save again, and confirm the two
        # checkpoints' adapter weights differ (proves the optimizer step
        # actually updated parameters, not just that files got written).
        config = _config("wan2.2-ti2v-5b", max_train_steps=4, checkpoint_every=2)
        lora_config = Wan22LoRAConfig.from_training_config(config)
        backend = build_smoke_test_backend(base_model_id=config.base_model_id, learning_rate=0.5, seed=0)
        store = FilesystemCheckpointStore(tmp_path / "checkpoints")
        writer = Wan22CheckpointWriter(store)
        trainer = Wan22LoRATrainer(
            backend=backend, checkpoint_writer=writer, dataset_entries=_entries(3), lora_config=lora_config,
            output_dir=tmp_path / "output",
        )

        result = trainer.train(config)
        assert result.status == "completed", result.error_message

        from safetensors.torch import load_file

        step2_weights = load_file(tmp_path / "output" / "adapters" / "unified" / "step_000002" / "adapter_model.safetensors")
        step4_weights = load_file(tmp_path / "output" / "adapters" / "unified" / "step_000004" / "adapter_model.safetensors")
        assert set(step2_weights) == set(step4_weights)
        assert any(not torch.equal(step2_weights[k], step4_weights[k]) for k in step2_weights)

    def test_changing_lora_config_mid_run_for_same_expert_raises(self):
        backend = build_smoke_test_backend(base_model_id="wan2.2-ti2v-5b", seed=0)
        lora_a = LoRAConfig(rank=4, alpha=8, target_modules=("to_q", "to_k", "to_v", "to_out.0"))
        lora_b = LoRAConfig(rank=8, alpha=16, target_modules=("to_q", "to_k", "to_v", "to_out.0"))
        entry = _entries(1)[0]

        backend.train_step(expert="unified", step=1, batch=entry, lora_config=lora_a)
        with pytest.raises(ValueError, match="cannot change mid-run"):
            backend.train_step(expert="unified", step=2, batch=entry, lora_config=lora_b)

    def test_save_checkpoint_before_train_step_raises(self, tmp_path):
        from training import ModelUnavailableError

        backend = build_smoke_test_backend(base_model_id="wan2.2-ti2v-5b", seed=0)

        with pytest.raises(ModelUnavailableError, match="before any train_step"):
            backend.save_checkpoint(expert="unified", step=1, output_dir=tmp_path)
