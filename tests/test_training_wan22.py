"""Tests for services/training/src/training/wan22 - the real Wan2.2
training execution *layer* (config loading, dataset manifest building,
LoRA config expansion, checkpoint pairing, the ITrainer orchestration
loop, evaluation hooks, and Kaggle/Modal dispatch wiring). No GPU is
used, no model is downloaded, and no real training happens anywhere in
this file: the only `IWan22TrainingBackend` that exists
(`UnavailableWan22Backend`) always raises `ModelUnavailableError`, and
every test that exercises `Wan22LoRATrainer.train()` asserts exactly
that failure - proving the orchestration is real and wired end-to-end
without ever touching real weights.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from training import (
    BASE_MODEL_REGISTRY,
    ApprovalRecord,
    CostGuard,
    DurationConformanceMetric,
    ExperimentConfigGenerator,
    ExperimentTier,
    FilesystemCheckpointStore,
    GPUType,
    InMemoryApprovalStore,
    InMemoryCheckpointStore,
    InMemoryJobStatusStore,
    InMemoryUsageLedger,
    KaggleClient,
    KaggleKernelRef,
    LoRAConfig,
    ModalJobLauncher,
    OutputExistsMetric,
    PairedCheckpointMissingError,
    TrainingConfig,
    TrainingController,
    UnavailableWan22Backend,
    Wan22CheckpointWriter,
    Wan22DatasetAdapter,
    Wan22EvaluationHook,
    Wan22LoRAConfig,
    Wan22LoRATrainer,
    Wan22ManifestEntry,
    build_training_command,
    build_training_command_for_job,
    dispatch_via_kaggle,
    dispatch_via_modal,
    expected_experts,
    expert_checkpoint_id,
    load_manifest_jsonl,
    write_job_inputs,
)
from training.dataset.metadata import ClipMetadata
from training.dataset.records import ClipRecord
from training.evaluation.benchmark import BenchmarkCase
from video_engine_adapter.adapters import SallehlyModelAdapter, Wan21Adapter
from video_engine_adapter.compute import LocalProvider
from video_engine_sdk import RenderSpec

_SPEC = RenderSpec(
    schema_version="1.0",
    shot_id="shot_1",
    duration_sec=4.0,
    fps=24,
    resolution="1280x720",
    positive_prompt="a cinematic product shot",
    mode="text_to_video",
)


def _clip_metadata(**overrides) -> ClipMetadata:
    base = dict(duration_sec=5.0, width=960, height=544, fps=16.0, codec="h264", size_bytes=1_000_000, file_hash="a" * 64)
    base.update(overrides)
    return ClipMetadata(**base)


def _clip_record(clip_id: str, **overrides) -> ClipRecord:
    base = dict(
        clip_id=clip_id,
        source_uri=f"file:///data/{clip_id}.mp4",
        metadata=_clip_metadata(),
        caption=f"a caption for {clip_id}",
        split="train",
        rights_cleared=True,
    )
    base.update(overrides)
    return ClipRecord(**base)


def _training_config(**overrides) -> TrainingConfig:
    base_kwargs = dict(
        schema_version="1.0",
        run_id="run-wan22-001",
        base_model_id="wan2.2-ti2v-5b",
        base_model_revision="2.2.0",
        strategy="lora",
        dataset_version="ds-abc123",
        resolution="960x544",
        fps=16,
        max_frames=81,
        learning_rate=1e-4,
        batch_size=1,
        gradient_accumulation_steps=4,
        max_train_steps=6,
        mixed_precision="bf16",
        min_vram_gb=16.0,
        gpu_count=1,
        checkpoint_every_steps=3,
        eval_every_steps=3,
        seed=42,
        lora=LoRAConfig(rank=16, alpha=32, target_modules=("to_q", "to_k", "to_v", "to_out.0")),
    )
    base_kwargs.update(overrides)
    return TrainingConfig(**base_kwargs)


def _fake_result(stdout: str = "", returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


# --------------------------------------------------------------------------
# BASE_MODEL_REGISTRY
# --------------------------------------------------------------------------


def test_all_three_wan22_variants_registered_and_apache_licensed():
    for model_id in ("wan2.2-ti2v-5b", "wan2.2-t2v-a14b", "wan2.2-i2v-a14b"):
        assert model_id in BASE_MODEL_REGISTRY
        info = BASE_MODEL_REGISTRY[model_id]
        assert info.license == "Apache-2.0"
        assert info.commercial_use_verified is True


# --------------------------------------------------------------------------
# expected_experts / Wan22LoRAConfig
# --------------------------------------------------------------------------


class TestExpectedExperts:
    def test_a14b_variants_require_two_experts(self):
        assert expected_experts("wan2.2-t2v-a14b") == frozenset({"high_noise", "low_noise"})
        assert expected_experts("wan2.2-i2v-a14b") == frozenset({"high_noise", "low_noise"})

    def test_ti2v_5b_requires_one_expert(self):
        assert expected_experts("wan2.2-ti2v-5b") == frozenset({"unified"})

    def test_unknown_model_id_raises(self):
        with pytest.raises(ValueError, match="Unknown Wan2.2 base_model_id"):
            expected_experts("wan2.1")


class TestWan22LoRAConfig:
    def test_from_training_config_unified_variant(self):
        config = _training_config(base_model_id="wan2.2-ti2v-5b")
        lora_config = Wan22LoRAConfig.from_training_config(config)
        assert set(lora_config.experts) == {"unified"}
        lora_config.validate()  # must not raise

    def test_from_training_config_a14b_variant_duplicates_lora_to_both_experts(self):
        config = _training_config(base_model_id="wan2.2-t2v-a14b")
        lora_config = Wan22LoRAConfig.from_training_config(config)
        assert set(lora_config.experts) == {"high_noise", "low_noise"}
        assert lora_config.experts["high_noise"] == config.lora
        assert lora_config.experts["low_noise"] == config.lora

    def test_from_training_config_a14b_variant_with_asymmetric_low_noise(self):
        config = _training_config(base_model_id="wan2.2-i2v-a14b")
        low_noise = LoRAConfig(rank=8, alpha=16, target_modules=("to_q", "to_k"))
        lora_config = Wan22LoRAConfig.from_training_config(config, low_noise_lora=low_noise)
        assert lora_config.experts["low_noise"] is low_noise
        assert lora_config.experts["high_noise"] is config.lora

    def test_from_training_config_rejects_low_noise_override_for_unified_variant(self):
        config = _training_config(base_model_id="wan2.2-ti2v-5b")
        with pytest.raises(ValueError, match="unified"):
            Wan22LoRAConfig.from_training_config(config, low_noise_lora=LoRAConfig())

    def test_from_training_config_requires_lora(self):
        config = _training_config(base_model_id="wan2.2-ti2v-5b", strategy="full_finetune", lora=None)
        with pytest.raises(ValueError, match="TrainingConfig.lora is required"):
            Wan22LoRAConfig.from_training_config(config)

    def test_validate_rejects_incomplete_expert_set_for_a14b(self):
        bad = Wan22LoRAConfig(base_model_id="wan2.2-t2v-a14b", experts={"high_noise": LoRAConfig()})
        with pytest.raises(ValueError, match="must configure exactly the experts"):
            bad.validate()

    def test_validate_rejects_extra_expert_for_unified_variant(self):
        bad = Wan22LoRAConfig(
            base_model_id="wan2.2-ti2v-5b", experts={"unified": LoRAConfig(), "high_noise": LoRAConfig()}
        )
        with pytest.raises(ValueError, match="must configure exactly the experts"):
            bad.validate()

    def test_yaml_round_trip(self, tmp_path):
        config = _training_config(base_model_id="wan2.2-t2v-a14b")
        lora_config = Wan22LoRAConfig.from_training_config(config)
        path = tmp_path / "wan22_lora.yaml"
        lora_config.to_yaml(path)
        reloaded = Wan22LoRAConfig.from_yaml(path)
        assert reloaded == lora_config


# --------------------------------------------------------------------------
# Wan22DatasetAdapter
# --------------------------------------------------------------------------


class TestWan22DatasetAdapter:
    def test_build_manifest_filters_by_split_and_maps_fields(self):
        config = _training_config()
        adapter = Wan22DatasetAdapter(config)
        records = [
            _clip_record("clip_a", split="train"),
            _clip_record("clip_b", split="val"),
            _clip_record("clip_c", split="train"),
        ]
        entries = adapter.build_manifest(records, split="train")
        assert {e.clip_id for e in entries} == {"clip_a", "clip_c"}
        assert entries[0].caption == "a caption for clip_a"
        assert entries[0].width == 960
        assert entries[0].height == 544

    def test_build_manifest_caps_num_frames_at_config_max_frames(self):
        config = _training_config(max_frames=40)
        adapter = Wan22DatasetAdapter(config)
        # duration_sec=5.0 * fps=16.0 = 80 raw frames, capped to 40
        entries = adapter.build_manifest([_clip_record("clip_a")])
        assert entries[0].num_frames == 40

    def test_build_manifest_rejects_clip_without_rights_clearance(self):
        adapter = Wan22DatasetAdapter(_training_config())
        with pytest.raises(ValueError, match="not rights_cleared"):
            adapter.build_manifest([_clip_record("clip_a", rights_cleared=False)])

    def test_build_manifest_rejects_clip_without_caption(self):
        adapter = Wan22DatasetAdapter(_training_config())
        with pytest.raises(ValueError, match="no caption"):
            adapter.build_manifest([_clip_record("clip_a", caption=None)])

    def test_build_manifest_rejects_empty_result(self):
        adapter = Wan22DatasetAdapter(_training_config())
        with pytest.raises(ValueError, match="would be empty"):
            adapter.build_manifest([_clip_record("clip_a", split="val")], split="train")

    def test_write_manifest_jsonl_and_load_round_trip(self, tmp_path):
        config = _training_config()
        adapter = Wan22DatasetAdapter(config)
        records = [_clip_record("clip_a"), _clip_record("clip_b")]
        path = adapter.write_manifest_jsonl(records, tmp_path / "manifest.jsonl")

        loaded = load_manifest_jsonl(path)
        assert len(loaded) == 2
        assert {e.clip_id for e in loaded} == {"clip_a", "clip_b"}
        assert all(isinstance(e, Wan22ManifestEntry) for e in loaded)


# --------------------------------------------------------------------------
# Wan22CheckpointWriter
# --------------------------------------------------------------------------


class TestWan22CheckpointWriter:
    def test_expert_checkpoint_id_is_deterministic(self):
        assert expert_checkpoint_id("run-1", 100, "high_noise") == "ckpt_run-1_000100_high_noise"

    def test_save_and_get_paired_checkpoints(self):
        writer = Wan22CheckpointWriter(InMemoryCheckpointStore())
        writer.save_expert_checkpoint(run_id="run-1", step=100, expert="high_noise", artifact_uri="s3://x/high")
        writer.save_expert_checkpoint(run_id="run-1", step=100, expert="low_noise", artifact_uri="s3://x/low")

        found = writer.get_paired_checkpoints("run-1", 100, {"high_noise", "low_noise"})
        assert set(found) == {"high_noise", "low_noise"}
        assert found["high_noise"].artifact_uri == "s3://x/high"

    def test_get_paired_checkpoints_raises_when_one_expert_missing(self):
        writer = Wan22CheckpointWriter(InMemoryCheckpointStore())
        writer.save_expert_checkpoint(run_id="run-1", step=100, expert="high_noise", artifact_uri="s3://x/high")

        with pytest.raises(PairedCheckpointMissingError, match="low_noise"):
            writer.get_paired_checkpoints("run-1", 100, {"high_noise", "low_noise"})

    def test_filesystem_checkpoint_store_persists_expert_checkpoints(self, tmp_path):
        store = FilesystemCheckpointStore(tmp_path)
        writer = Wan22CheckpointWriter(store)
        writer.save_expert_checkpoint(run_id="run-1", step=50, expert="unified", artifact_uri="file:///x")

        store2 = FilesystemCheckpointStore(tmp_path)
        writer2 = Wan22CheckpointWriter(store2)
        found = writer2.get_paired_checkpoints("run-1", 50, {"unified"})
        assert found["unified"].step == 50

    def test_latest_paired_step_returns_none_for_a_fresh_run(self):
        writer = Wan22CheckpointWriter(InMemoryCheckpointStore())
        assert writer.latest_paired_step("run-1", {"unified"}) is None

    def test_latest_paired_step_returns_the_highest_fully_paired_step(self):
        writer = Wan22CheckpointWriter(InMemoryCheckpointStore())
        writer.save_expert_checkpoint(run_id="run-1", step=2, expert="high_noise", artifact_uri="s3://x/h2")
        writer.save_expert_checkpoint(run_id="run-1", step=2, expert="low_noise", artifact_uri="s3://x/l2")
        writer.save_expert_checkpoint(run_id="run-1", step=4, expert="high_noise", artifact_uri="s3://x/h4")
        writer.save_expert_checkpoint(run_id="run-1", step=4, expert="low_noise", artifact_uri="s3://x/l4")

        assert writer.latest_paired_step("run-1", {"high_noise", "low_noise"}) == 4

    def test_latest_paired_step_skips_a_step_with_only_some_experts_saved(self):
        # Simulates a crash mid-checkpoint: step 4 only got one of two
        # experts saved before the run died - resuming must fall back to
        # the last step where *both* experts have a real checkpoint.
        writer = Wan22CheckpointWriter(InMemoryCheckpointStore())
        writer.save_expert_checkpoint(run_id="run-1", step=2, expert="high_noise", artifact_uri="s3://x/h2")
        writer.save_expert_checkpoint(run_id="run-1", step=2, expert="low_noise", artifact_uri="s3://x/l2")
        writer.save_expert_checkpoint(run_id="run-1", step=4, expert="high_noise", artifact_uri="s3://x/h4")

        assert writer.latest_paired_step("run-1", {"high_noise", "low_noise"}) == 2


# --------------------------------------------------------------------------
# Wan22LoRATrainer (the ITrainer orchestration loop)
# --------------------------------------------------------------------------


class TestWan22LoRATrainer:
    def _manifest(self) -> list[Wan22ManifestEntry]:
        return [
            Wan22ManifestEntry(
                clip_id="clip_a", video_path="file:///a.mp4", caption="a scene",
                width=960, height=544, num_frames=81, fps=16.0,
            )
        ]

    def test_train_with_unavailable_backend_fails_cleanly_on_first_step(self):
        config = _training_config(base_model_id="wan2.2-ti2v-5b")
        lora_config = Wan22LoRAConfig.from_training_config(config)
        trainer = Wan22LoRATrainer(
            backend=UnavailableWan22Backend(),
            checkpoint_writer=Wan22CheckpointWriter(InMemoryCheckpointStore()),
            dataset_entries=self._manifest(),
            lora_config=lora_config,
            output_dir="/tmp/wan22-test-output",
        )

        result = trainer.train(config)

        assert result.status == "failed"
        assert result.final_step == 1
        assert result.checkpoint_ids == []
        assert "Wan2.2 training backend unavailable" in result.error_message

    def test_train_rejects_base_model_id_mismatch(self):
        config = _training_config(base_model_id="wan2.2-ti2v-5b")
        mismatched_lora_config = Wan22LoRAConfig.from_training_config(
            _training_config(base_model_id="wan2.2-t2v-a14b")
        )
        trainer = Wan22LoRATrainer(
            backend=UnavailableWan22Backend(),
            checkpoint_writer=Wan22CheckpointWriter(InMemoryCheckpointStore()),
            dataset_entries=self._manifest(),
            lora_config=mismatched_lora_config,
            output_dir="/tmp/wan22-test-output",
        )
        with pytest.raises(ValueError, match="does not match"):
            trainer.train(config)

    def test_train_rejects_empty_dataset(self):
        config = _training_config(base_model_id="wan2.2-ti2v-5b")
        lora_config = Wan22LoRAConfig.from_training_config(config)
        trainer = Wan22LoRATrainer(
            backend=UnavailableWan22Backend(),
            checkpoint_writer=Wan22CheckpointWriter(InMemoryCheckpointStore()),
            dataset_entries=[],
            lora_config=lora_config,
            output_dir="/tmp/wan22-test-output",
        )
        with pytest.raises(ValueError, match="no dataset entries"):
            trainer.train(config)

    def test_train_with_working_fake_backend_pairs_both_experts_every_checkpoint(self):
        """Proves the orchestration loop's real behavior (step counting,
        round-robin batching, checkpoint cadence, both-experts-paired
        invariant) using a fake backend that succeeds - the only way to
        observe that shape without a real GPU."""
        from training.wan22.backend import IWan22TrainingBackend, TrainStepResult

        class FakeSucceedingBackend(IWan22TrainingBackend):
            def __init__(self):
                self.steps = []

            def train_step(self, *, expert, step, batch, lora_config):
                self.steps.append((expert, step, batch.clip_id))
                return TrainStepResult(loss=1.0 / step)

            def save_checkpoint(self, *, expert, step, output_dir):
                return f"fake://{output_dir}/{expert}/{step}"

        config = _training_config(base_model_id="wan2.2-t2v-a14b", max_train_steps=4, checkpoint_every_steps=2)
        lora_config = Wan22LoRAConfig.from_training_config(config)
        backend = FakeSucceedingBackend()
        checkpoint_store = InMemoryCheckpointStore()
        writer = Wan22CheckpointWriter(checkpoint_store)
        checkpoint_events = []

        trainer = Wan22LoRATrainer(
            backend=backend,
            checkpoint_writer=writer,
            dataset_entries=self._manifest(),
            lora_config=lora_config,
            output_dir="/tmp/wan22-test-output",
            on_checkpoint=lambda step, ids: checkpoint_events.append((step, ids)),
        )

        result = trainer.train(config)

        assert result.status == "completed"
        assert result.final_step == 4
        # Both experts trained at every one of the 4 steps.
        experts_per_step = {}
        for expert, step, _clip in backend.steps:
            experts_per_step.setdefault(step, set()).add(expert)
        assert all(experts == {"high_noise", "low_noise"} for experts in experts_per_step.values())
        # Checkpoints at steps 2 and 4, both experts paired at each.
        assert [step for step, _ in checkpoint_events] == [2, 4]
        for step in (2, 4):
            paired = writer.get_paired_checkpoints(config.run_id, step, {"high_noise", "low_noise"})
            assert set(paired) == {"high_noise", "low_noise"}
        assert len(result.checkpoint_ids) == 4  # 2 experts x 2 checkpoint steps

    def test_train_resumes_from_a_previously_paired_checkpoint(self):
        """A run that already has a paired checkpoint at step 2 for both
        experts (e.g. a previous process died after step 2) must resume
        from there - loading each expert's saved checkpoint and
        continuing global_step from 2, not restarting at step 0 and not
        redoing steps 1-2."""
        from training.wan22.backend import IWan22TrainingBackend, TrainStepResult

        class FakeResumableBackend(IWan22TrainingBackend):
            def __init__(self):
                self.steps: list[tuple[str, int]] = []
                self.loaded: list[tuple[str, str]] = []

            def train_step(self, *, expert, step, batch, lora_config):
                self.steps.append((expert, step))
                return TrainStepResult(loss=1.0)

            def save_checkpoint(self, *, expert, step, output_dir):
                return f"fake://{output_dir}/{expert}/{step}"

            def load_checkpoint(self, *, expert, artifact_uri, lora_config):
                self.loaded.append((expert, artifact_uri))

        config = _training_config(base_model_id="wan2.2-t2v-a14b", max_train_steps=4, checkpoint_every_steps=2)
        lora_config = Wan22LoRAConfig.from_training_config(config)
        backend = FakeResumableBackend()
        checkpoint_store = InMemoryCheckpointStore()
        writer = Wan22CheckpointWriter(checkpoint_store)
        # Simulate a prior run that already completed and checkpointed step 2.
        writer.save_expert_checkpoint(run_id=config.run_id, step=2, expert="high_noise", artifact_uri="fake://prior/high_noise/2")
        writer.save_expert_checkpoint(run_id=config.run_id, step=2, expert="low_noise", artifact_uri="fake://prior/low_noise/2")

        trainer = Wan22LoRATrainer(
            backend=backend, checkpoint_writer=writer, dataset_entries=self._manifest(),
            lora_config=lora_config, output_dir="/tmp/wan22-test-output",
        )

        result = trainer.train(config)

        assert result.status == "completed"
        assert result.final_step == 4
        assert set(backend.loaded) == {
            ("high_noise", "fake://prior/high_noise/2"), ("low_noise", "fake://prior/low_noise/2"),
        }
        # Only steps 3 and 4 actually ran - steps 1-2 were not redone.
        steps_trained = sorted({step for _expert, step in backend.steps})
        assert steps_trained == [3, 4]

    def test_train_does_not_attempt_resume_for_a_fresh_run(self):
        # No prior checkpoint exists, so load_checkpoint must never be
        # called and training starts at step 1 as normal.
        from training.wan22.backend import IWan22TrainingBackend, TrainStepResult

        class FakeBackendThatFailsOnLoad(IWan22TrainingBackend):
            def train_step(self, *, expert, step, batch, lora_config):
                return TrainStepResult(loss=1.0)

            def save_checkpoint(self, *, expert, step, output_dir):
                return f"fake://{output_dir}/{expert}/{step}"

            def load_checkpoint(self, *, expert, artifact_uri, lora_config):
                raise AssertionError("load_checkpoint must not be called for a fresh run")

        config = _training_config(base_model_id="wan2.2-ti2v-5b", max_train_steps=2, checkpoint_every_steps=2)
        lora_config = Wan22LoRAConfig.from_training_config(config)
        trainer = Wan22LoRATrainer(
            backend=FakeBackendThatFailsOnLoad(), checkpoint_writer=Wan22CheckpointWriter(InMemoryCheckpointStore()),
            dataset_entries=self._manifest(), lora_config=lora_config, output_dir="/tmp/wan22-test-output",
        )

        result = trainer.train(config)

        assert result.status == "completed"
        assert result.final_step == 2


# --------------------------------------------------------------------------
# TrainingCommand / build_training_command
# --------------------------------------------------------------------------


class TestTrainingCommand:
    def test_to_argv_shape(self):
        command = build_training_command("job-1", base_dir="/tmp/runs")
        argv = command.to_argv(python="python3")
        assert argv[0] == "python3"
        assert argv[1] == command.entrypoint
        assert "--config" in argv and "/tmp/runs/job-1/config.yaml" in argv
        assert "--job-id" in argv and "job-1" in argv

    def test_to_modal_extra_args_shape(self):
        command = build_training_command("job-1", base_dir="/tmp/runs", extra_args={"expert": "unified"})
        args = command.to_modal_extra_args()
        assert args["job-id"] == "job-1"
        assert args["config"] == "/tmp/runs/job-1/config.yaml"
        assert args["expert"] == "unified"


# --------------------------------------------------------------------------
# TrainingController integration (item 7)
# --------------------------------------------------------------------------


class TestControllerIntegration:
    def test_build_training_command_for_planned_job(self):
        controller = TrainingController(
            job_store=InMemoryJobStatusStore(),
            config_generator=ExperimentConfigGenerator(allowed_ranges={"learning_rate": (1e-6, 1e-3)}),
        )
        job = controller.plan_experiment(
            base_config=_training_config(),
            overrides={},
            tier=ExperimentTier.FREE_GPU,
            provider="modal",
            job_id="job-wan22-1",
        )

        command = build_training_command_for_job(job, base_dir="/tmp/runs")

        assert command.job_id == "job-wan22-1"
        assert command.config_path == "/tmp/runs/job-wan22-1/config.yaml"

    def test_write_job_inputs_serializes_config_to_disk(self, tmp_path):
        controller = TrainingController(
            job_store=InMemoryJobStatusStore(),
            config_generator=ExperimentConfigGenerator(allowed_ranges={}),
        )
        job = controller.plan_experiment(
            base_config=_training_config(), overrides={}, tier=ExperimentTier.FREE_GPU,
            provider="kaggle", job_id="job-wan22-2",
        )
        command = build_training_command_for_job(job, base_dir=str(tmp_path))

        write_job_inputs(job, command)

        reloaded = TrainingConfig.from_yaml(command.config_path)
        assert reloaded.run_id == job.config.run_id
        assert reloaded.base_model_id == "wan2.2-ti2v-5b"


# --------------------------------------------------------------------------
# Kaggle / Modal dispatch wiring (item 8)
# --------------------------------------------------------------------------


class TestDispatchWiring:
    def _planned_job(self, tmp_path, provider="kaggle", **command_kwargs):
        controller = TrainingController(
            job_store=InMemoryJobStatusStore(),
            config_generator=ExperimentConfigGenerator(allowed_ranges={}),
        )
        job = controller.plan_experiment(
            base_config=_training_config(), overrides={}, tier=ExperimentTier.FREE_GPU,
            provider=provider, job_id="job-dispatch-1",
        )
        command = build_training_command_for_job(job, base_dir=str(tmp_path), **command_kwargs)
        return job, command

    def test_dispatch_via_kaggle_uploads_input_dataset_then_pushes_runnable_kernel(self, tmp_path):
        # A plain Kaggle kernel push cannot receive CLI arguments
        # (docs/adr/0025-kaggle-dispatch-argv-fix.md) - dispatch_via_kaggle()
        # now uploads config.yaml/dataset_manifest.jsonl as a real Kaggle
        # dataset first, then pushes kaggle_kernel_runner.py (not
        # wan22_lora_train.py directly) referencing that dataset. Point
        # the entrypoint at a scratch directory under tmp_path rather
        # than the real services/training/entrypoints/, so this test
        # never touches the source tree.
        fake_entrypoint_dir = tmp_path / "fake_entrypoints"
        fake_entrypoint_dir.mkdir()
        (fake_entrypoint_dir / "wan22_lora_train.py").write_text("# fake entrypoint for tests\n")
        (fake_entrypoint_dir / "kaggle_kernel_runner.py").write_text("# fake runner for tests\n")
        job, command = self._planned_job(
            tmp_path, provider="kaggle", entrypoint=str(fake_entrypoint_dir / "wan22_lora_train.py"),
        )
        # dispatch_via_kaggle() expects the dataset manifest to already
        # exist on disk (built ahead of time by ingest_dataset.py, per
        # write_job_inputs()'s own docstring) - create a fake one here.
        Path(command.dataset_manifest_path).parent.mkdir(parents=True, exist_ok=True)
        Path(command.dataset_manifest_path).write_text('{"clip_id": "c1"}\n')

        calls = []

        def runner(args):
            calls.append(args)
            return _fake_result(stdout="Kernel version pushed")

        client = KaggleClient(runner=runner)
        kernel_ref = KaggleKernelRef(owner_slug="sallehly", kernel_slug=job.job_id)

        output = dispatch_via_kaggle(job, command, client, kernel_ref, git_ref="claude/sallehly-engine-audit-vnxs4f")

        assert output == "Kernel version pushed"
        # Two real CLI calls: create the input dataset, then push the kernel.
        assert calls[0][:3] == ["kaggle", "datasets", "create"]
        assert calls[1][:3] == ["kaggle", "kernels", "push"]
        # The config was written to disk as a real side effect of dispatch.
        assert TrainingConfig.from_yaml(command.config_path).run_id == job.config.run_id
        # The uploaded dataset staging dir actually contains all three real inputs -
        # including git_ref.txt, so the Kaggle-side clone checks out the right
        # branch instead of silently falling back to the repo's default branch.
        staged_dir = Path(command.config_path).parent / "kaggle_dataset_input"
        assert (staged_dir / "config.yaml").is_file()
        assert (staged_dir / "dataset_manifest.jsonl").is_file()
        assert (staged_dir / "git_ref.txt").read_text() == "claude/sallehly-engine-audit-vnxs4f"
        # Real failure found live in CI: `kaggle datasets create` rejects
        # the whole dispatch with "Subtitle length must be between 20 and
        # 80 characters" if this drifts outside that range - assert the
        # actual bound Kaggle's API enforces, not just that it's non-empty.
        create_call = calls[0]
        dataset_metadata_path = (
            Path(create_call[create_call.index("-p") + 1]) / "dataset-metadata.json"
        )
        subtitle = json.loads(dataset_metadata_path.read_text())["subtitle"]
        assert 20 <= len(subtitle) <= 80

    def test_dispatch_via_kaggle_defaults_git_ref_to_master(self, tmp_path):
        fake_entrypoint_dir = tmp_path / "fake_entrypoints"
        fake_entrypoint_dir.mkdir()
        (fake_entrypoint_dir / "wan22_lora_train.py").write_text("# fake entrypoint for tests\n")
        job, command = self._planned_job(
            tmp_path, provider="kaggle", entrypoint=str(fake_entrypoint_dir / "wan22_lora_train.py"),
        )
        Path(command.dataset_manifest_path).parent.mkdir(parents=True, exist_ok=True)
        Path(command.dataset_manifest_path).write_text('{"clip_id": "c1"}\n')
        client = KaggleClient(runner=lambda args: _fake_result(stdout="Kernel version pushed"))
        kernel_ref = KaggleKernelRef(owner_slug="sallehly", kernel_slug=job.job_id)

        dispatch_via_kaggle(job, command, client, kernel_ref)

        staged_dir = Path(command.config_path).parent / "kaggle_dataset_input"
        assert (staged_dir / "git_ref.txt").read_text() == "master"

    def test_dispatch_via_kaggle_requires_dataset_manifest_to_already_exist(self, tmp_path):
        fake_entrypoint_dir = tmp_path / "fake_entrypoints"
        fake_entrypoint_dir.mkdir()
        (fake_entrypoint_dir / "wan22_lora_train.py").write_text("# fake entrypoint for tests\n")
        job, command = self._planned_job(
            tmp_path, provider="kaggle", entrypoint=str(fake_entrypoint_dir / "wan22_lora_train.py"),
        )
        client = KaggleClient(runner=lambda args: _fake_result(stdout="unused"))
        kernel_ref = KaggleKernelRef(owner_slug="sallehly", kernel_slug=job.job_id)

        with pytest.raises(FileNotFoundError):
            dispatch_via_kaggle(job, command, client, kernel_ref)

    def test_dispatch_via_modal_launches_with_gpu_and_extra_args(self, tmp_path):
        job, command = self._planned_job(tmp_path, provider="modal")
        calls = []

        def runner(args):
            calls.append(args)
            return _fake_result(stdout="Created app ap-wan22test\n")

        launcher = ModalJobLauncher(runner=runner)

        handle = dispatch_via_modal(
            job, command, launcher,
            gpu_type=GPUType.T4, function_timeout_sec=3600, max_wall_clock_sec=7200,
        )

        assert handle.app_name == "ap-wan22test"
        assert calls[0][:4] == ["modal", "run", "--detach", f"{command.entrypoint}::train_wan22_lora"]
        assert "--job-id" in calls[0]
        assert TrainingConfig.from_yaml(command.config_path).base_model_id == "wan2.2-ti2v-5b"

    def test_dispatch_requires_cost_guard_approval_for_paid_tier_job(self, tmp_path):
        # Sanity check that Wan2.2 dispatch doesn't bypass CostGuard -
        # planning a PAID_GPU job still requires prior approval, exactly
        # as it does for any other base model.
        approvals = InMemoryApprovalStore()
        guard = CostGuard(approval_store=approvals, usage_ledger=InMemoryUsageLedger(), monthly_budget_usd=100.0)
        controller = TrainingController(
            job_store=InMemoryJobStatusStore(),
            config_generator=ExperimentConfigGenerator(allowed_ranges={}),
            cost_guard=guard,
        )
        from training.automation import ApprovalRequiredError

        with pytest.raises(ApprovalRequiredError):
            controller.plan_experiment(
                base_config=_training_config(), overrides={}, tier=ExperimentTier.PAID_GPU,
                provider="runpod", estimated_cost_usd=20.0, job_id="job-wan22-paid-1",
            )

        approvals.request(ApprovalRecord(job_id="job-wan22-paid-1", requested_by="agent", max_cost_usd=50.0))
        approvals.approve("job-wan22-paid-1", approved_by="human")
        job = controller.plan_experiment(
            base_config=_training_config(), overrides={}, tier=ExperimentTier.PAID_GPU,
            provider="runpod", estimated_cost_usd=20.0, job_id="job-wan22-paid-1",
        )
        assert job.job_id == "job-wan22-paid-1"


# --------------------------------------------------------------------------
# Wan22EvaluationHook (item 6) - exercised against real, offline engines
# --------------------------------------------------------------------------


class TestWan22EvaluationHook:
    def test_hook_runs_real_benchmark_against_wan21_adapter_and_records_report(self, tmp_path):
        hook = Wan22EvaluationHook(
            engine=Wan21Adapter(),
            compute_provider=LocalProvider(str(tmp_path)),
            cases=[BenchmarkCase(case_id="case_1", render_spec=_SPEC)],
            metrics=[DurationConformanceMetric(), OutputExistsMetric()],
        )

        report = hook(step=100, checkpoint_ids=["ckpt_a", "ckpt_b"])

        assert report.version_id == "step-000100"
        assert report.error_count == 0
        assert hook.report_for_step(100) is report

    def test_hook_against_untrained_sallehly_adapter_degrades_gracefully(self, tmp_path):
        hook = Wan22EvaluationHook(
            engine=SallehlyModelAdapter(),
            compute_provider=LocalProvider(str(tmp_path)),
            cases=[BenchmarkCase(case_id="case_1", render_spec=_SPEC)],
            metrics=[DurationConformanceMetric()],
        )

        report = hook(step=1, checkpoint_ids=[])

        # Same graceful-degradation contract BenchmarkRunner itself
        # proves against SallehlyModelAdapter - a per-case error, not a
        # crash.
        assert report.error_count == 1

    def test_regression_against_compares_two_recorded_steps(self, tmp_path):
        hook = Wan22EvaluationHook(
            engine=Wan21Adapter(),
            compute_provider=LocalProvider(str(tmp_path)),
            cases=[BenchmarkCase(case_id="case_1", render_spec=_SPEC)],
            metrics=[DurationConformanceMetric()],
        )
        hook(step=100, checkpoint_ids=[])
        hook(step=200, checkpoint_ids=[])

        findings = hook.regression_against(100, 200)

        assert findings is not None
        assert isinstance(findings, list)

    def test_regression_against_missing_step_returns_none(self, tmp_path):
        hook = Wan22EvaluationHook(
            engine=Wan21Adapter(),
            compute_provider=LocalProvider(str(tmp_path)),
            cases=[BenchmarkCase(case_id="case_1", render_spec=_SPEC)],
            metrics=[DurationConformanceMetric()],
        )
        hook(step=100, checkpoint_ids=[])

        assert hook.regression_against(100, 999) is None
