"""Tests for services/training/src/training/automation - the Kaggle/Modal
CLI wrappers, cost-protection gate, and AI training controller built for
the zero/near-zero-cost autonomous training factory. No real network call
or `kaggle`/`modal` CLI invocation happens anywhere here: every client is
exercised with an injected fake `runner` callable in place of
subprocess.run, exactly like tests/test_runpod_provider.py does with
httpx.MockTransport. No GPU is rented, no model is downloaded, no
training is executed.
"""

from __future__ import annotations

import subprocess

import pytest
from training import BASE_MODEL_REGISTRY, LoRAConfig, TrainingConfig
from training.automation import (
    ApprovalRequiredError,
    ApprovalStatus,
    BudgetExceededError,
    CostGuard,
    DatasetMetadata,
    ExperimentConfigGenerator,
    ExperimentTier,
    FilesystemApprovalStore,
    FilesystemJobStatusStore,
    FilesystemUsageLedger,
    GPUType,
    InMemoryApprovalStore,
    InMemoryJobStatusStore,
    InMemoryUsageLedger,
    KaggleAutomationError,
    KaggleCLINotAvailableError,
    KaggleClient,
    KaggleDatasetRef,
    KaggleKernelRef,
    KaggleKernelStatus,
    KernelPushConfig,
    ModalAutomationError,
    ModalCLINotAvailableError,
    ModalJobConfig,
    ModalJobLauncher,
    TrainingController,
    UnapprovedConfigOverrideError,
    UsageRecord,
)


def _fake_result(stdout: str = "", returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def _base_training_config(**overrides) -> TrainingConfig:
    base_kwargs = dict(
        schema_version="1.0",
        run_id="run-001",
        base_model_id="wan2.1",
        base_model_revision="main",
        strategy="lora",
        dataset_version="ds-abc123",
        resolution="960x544",
        fps=16,
        max_frames=81,
        learning_rate=1e-4,
        batch_size=1,
        gradient_accumulation_steps=4,
        max_train_steps=1000,
        mixed_precision="bf16",
        min_vram_gb=16.0,
        gpu_count=1,
        checkpoint_every_steps=100,
        eval_every_steps=100,
        seed=42,
        lora=LoRAConfig(rank=16, alpha=32, target_modules=("to_q", "to_k", "to_v", "to_out.0")),
    )
    base_kwargs.update(overrides)
    return TrainingConfig(**base_kwargs)


# --------------------------------------------------------------------------
# KaggleClient
# --------------------------------------------------------------------------


class TestKaggleClient:
    def test_requires_cli_on_path_when_no_runner_injected(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda _name: None)
        with pytest.raises(KaggleCLINotAvailableError):
            KaggleClient()

    def test_upload_dataset_writes_metadata_and_runs_version_command(self, tmp_path):
        calls: list[list[str]] = []

        def runner(args):
            calls.append(args)
            return _fake_result(stdout="Dataset version created")

        client = KaggleClient(runner=runner)
        ref = KaggleDatasetRef(owner_slug="sallehly", dataset_slug="training-clips")
        metadata = DatasetMetadata(dataset_ref=ref, title="Training clips")

        output = client.upload_dataset(tmp_path, metadata, version_notes="add batch 2")

        assert output == "Dataset version created"
        assert (tmp_path / "dataset-metadata.json").exists()
        assert calls[0][:3] == ["kaggle", "datasets", "version"]
        assert "add batch 2" in calls[0]

    def test_upload_dataset_new_uses_create_command(self, tmp_path):
        calls = []

        def runner(args):
            calls.append(args)
            return _fake_result()

        client = KaggleClient(runner=runner)
        ref = KaggleDatasetRef(owner_slug="sallehly", dataset_slug="training-clips")
        client.upload_dataset(tmp_path, DatasetMetadata(dataset_ref=ref, title="x"), is_new=True)

        assert calls[0][:3] == ["kaggle", "datasets", "create"]

    def test_download_dataset_creates_dest_and_runs_download_command(self, tmp_path):
        calls = []

        def runner(args):
            calls.append(args)
            return _fake_result()

        client = KaggleClient(runner=runner)
        dest = tmp_path / "downloaded"
        ref = KaggleDatasetRef(owner_slug="sallehly", dataset_slug="training-clips")

        result = client.download_dataset(ref, dest)

        assert result == dest
        assert dest.exists()
        assert calls[0] == ["kaggle", "datasets", "download", "-d", "sallehly/training-clips", "-p", str(dest), "--unzip"]

    def test_push_kernel_writes_metadata_and_runs_push(self, tmp_path):
        calls = []

        def runner(args):
            calls.append(args)
            return _fake_result(stdout="Kernel pushed successfully")

        client = KaggleClient(runner=runner)
        kernel_ref = KaggleKernelRef(owner_slug="sallehly", kernel_slug="lora-smoke-test")
        dataset_ref = KaggleDatasetRef(owner_slug="sallehly", dataset_slug="training-clips")
        config = KernelPushConfig(
            kernel_ref=kernel_ref,
            title="LoRA smoke test",
            code_file="train.py",
            dataset_sources=(dataset_ref,),
        )

        output = client.push_kernel(tmp_path, config)

        assert output == "Kernel pushed successfully"
        metadata_path = tmp_path / "kernel-metadata.json"
        assert metadata_path.exists()
        import json

        written = json.loads(metadata_path.read_text())
        assert written["id"] == "sallehly/lora-smoke-test"
        assert written["enable_gpu"] is True
        assert written["dataset_sources"] == ["sallehly/training-clips"]

    def test_push_kernel_rejects_invalid_config(self, tmp_path):
        client = KaggleClient(runner=lambda args: _fake_result())
        bad_config = KernelPushConfig(
            kernel_ref=KaggleKernelRef(owner_slug="sallehly", kernel_slug="x"),
            title="",
            code_file="train.py",
        )
        with pytest.raises(ValueError):
            client.push_kernel(tmp_path, bad_config)

    def test_get_kernel_status_parses_complete(self):
        client = KaggleClient(runner=lambda args: _fake_result(stdout='sallehly/x has status "complete"'))
        status = client.get_kernel_status(KaggleKernelRef(owner_slug="sallehly", kernel_slug="x"))
        assert status == KaggleKernelStatus.COMPLETE
        assert status.is_terminal

    def test_get_kernel_status_running_is_not_terminal(self):
        client = KaggleClient(runner=lambda args: _fake_result(stdout='sallehly/x has status "running"'))
        status = client.get_kernel_status(KaggleKernelRef(owner_slug="sallehly", kernel_slug="x"))
        assert status == KaggleKernelStatus.RUNNING
        assert not status.is_terminal

    def test_get_kernel_status_unparseable_output_raises(self):
        client = KaggleClient(runner=lambda args: _fake_result(stdout="garbage, no status here"))
        with pytest.raises(KaggleAutomationError):
            client.get_kernel_status(KaggleKernelRef(owner_slug="sallehly", kernel_slug="x"))

    def test_get_kernel_status_parses_real_enum_repr(self):
        # Real `kernels status` output (confirmed by hand, run 30278022296)
        # prints the enum's own repr - "KernelWorkerStatus.RUNNING" - not
        # the bare "running" originally assumed.
        client = KaggleClient(
            runner=lambda args: _fake_result(stdout='sallehly/x has status "KernelWorkerStatus.RUNNING"')
        )
        status = client.get_kernel_status(KaggleKernelRef(owner_slug="sallehly", kernel_slug="x"))
        assert status == KaggleKernelStatus.RUNNING

    def test_get_kernel_status_parses_real_cancel_acknowledged(self):
        client = KaggleClient(
            runner=lambda args: _fake_result(stdout='sallehly/x has status "KernelWorkerStatus.CANCEL_ACKNOWLEDGED"')
        )
        status = client.get_kernel_status(KaggleKernelRef(owner_slug="sallehly", kernel_slug="x"))
        assert status == KaggleKernelStatus.CANCELLED

    def test_get_dataset_status_returns_stripped_stdout(self):
        client = KaggleClient(runner=lambda args: _fake_result(stdout="ready\n"))
        status = client.get_dataset_status(KaggleDatasetRef(owner_slug="sallehly", dataset_slug="x"))
        assert status == "ready"

    def test_command_failure_raises_kaggle_automation_error(self):
        client = KaggleClient(runner=lambda args: _fake_result(returncode=1, stderr="401 unauthorized"))
        with pytest.raises(KaggleAutomationError, match="401 unauthorized"):
            client.get_kernel_status(KaggleKernelRef(owner_slug="sallehly", kernel_slug="x"))

    def test_pull_kernel_output_creates_dest_dir(self, tmp_path):
        client = KaggleClient(runner=lambda args: _fake_result())
        dest = tmp_path / "output"
        result = client.pull_kernel_output(KaggleKernelRef(owner_slug="sallehly", kernel_slug="x"), dest)
        assert result == dest
        assert dest.exists()

    def test_poll_kernel_until_terminal_stops_on_complete(self):
        statuses = iter(['"queued"', '"running"', '"complete"'])
        calls = {"n": 0}

        def runner(args):
            calls["n"] += 1
            return _fake_result(stdout=next(statuses))

        client = KaggleClient(runner=runner)
        sleeps: list[float] = []

        result = client.poll_kernel_until_terminal(
            KaggleKernelRef(owner_slug="sallehly", kernel_slug="x"),
            poll_interval_sec=1.0,
            timeout_sec=100.0,
            sleep_fn=sleeps.append,
            clock=iter([0.0, 0.0, 1.0, 1.0, 2.0, 2.0]).__next__,
        )

        assert result.status == KaggleKernelStatus.COMPLETE
        assert calls["n"] == 3
        assert len(sleeps) == 2

    def test_poll_kernel_until_terminal_raises_on_timeout(self):
        client = KaggleClient(runner=lambda args: _fake_result(stdout='"running"'))
        clock_values = iter([0.0, 0.0, 50.0, 50.0, 200.0])
        with pytest.raises(KaggleAutomationError, match="Timed out"):
            client.poll_kernel_until_terminal(
                KaggleKernelRef(owner_slug="sallehly", kernel_slug="x"),
                poll_interval_sec=10.0,
                timeout_sec=100.0,
                sleep_fn=lambda _s: None,
                clock=clock_values.__next__,
            )


# --------------------------------------------------------------------------
# ModalJobLauncher
# --------------------------------------------------------------------------


class TestModalJobLauncher:
    def test_requires_cli_on_path_when_no_runner_injected(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda _name: None)
        with pytest.raises(ModalCLINotAvailableError):
            ModalJobLauncher()

    def test_job_config_rejects_ceiling_below_function_timeout(self):
        with pytest.raises(ValueError):
            ModalJobConfig(
                app_entrypoint="train.py",
                function_name="run_lora_smoke_test",
                gpu_type=GPUType.T4,
                function_timeout_sec=3600,
                max_wall_clock_sec=1800,
            ).validate()

    def test_launch_builds_detach_command_with_extra_args(self):
        calls = []

        def runner(args):
            calls.append(args)
            return _fake_result(stdout="Created app ap-AbCd1234\n")

        launcher = ModalJobLauncher(runner=runner)
        config = ModalJobConfig(
            app_entrypoint="train.py",
            function_name="run_lora_smoke_test",
            gpu_type=GPUType.T4,
            function_timeout_sec=1800,
            max_wall_clock_sec=3600,
            extra_args={"config-path": "configs/wan21_smoke.yaml"},
        )

        handle = launcher.launch(config)

        assert calls[0][:4] == ["modal", "run", "--detach", "train.py::run_lora_smoke_test"]
        assert "--config-path" in calls[0]
        assert handle.app_name == "ap-AbCd1234"

    def test_launch_falls_back_to_entrypoint_when_app_id_unparseable(self):
        launcher = ModalJobLauncher(runner=lambda args: _fake_result(stdout="no id printed here"))
        config = ModalJobConfig(
            app_entrypoint="train.py",
            function_name="run_lora_smoke_test",
            gpu_type=GPUType.T4,
            function_timeout_sec=60,
            max_wall_clock_sec=120,
        )
        handle = launcher.launch(config)
        assert handle.app_name == "train.py"

    def test_command_failure_raises_modal_automation_error(self):
        launcher = ModalJobLauncher(runner=lambda args: _fake_result(returncode=1, stderr="quota exceeded"))
        config = ModalJobConfig(
            app_entrypoint="train.py",
            function_name="run_lora_smoke_test",
            gpu_type=GPUType.A100,
            function_timeout_sec=60,
            max_wall_clock_sec=120,
        )
        with pytest.raises(ModalAutomationError, match="quota exceeded"):
            launcher.launch(config)

    def test_fetch_logs_appends_follow_flag(self):
        calls = []

        def runner(args):
            calls.append(args)
            return _fake_result(stdout="log line 1\n")

        launcher = ModalJobLauncher(runner=runner)
        from training.automation.modal_client import ModalJobHandle
        from datetime import datetime, timezone

        handle = ModalJobHandle(app_name="ap-test123", started_at=datetime.now(timezone.utc))
        launcher.fetch_logs(handle, follow=True)
        assert calls[0] == ["modal", "app", "logs", "ap-test123", "-f"]

    def test_enforce_wall_clock_ceiling_stops_when_exceeded(self):
        stop_calls = []

        def runner(args):
            if args[1] == "app" and args[2] == "stop":
                stop_calls.append(args)
            return _fake_result()

        launcher = ModalJobLauncher(runner=runner)
        from training.automation.modal_client import ModalJobHandle
        from datetime import datetime, timezone

        handle = ModalJobHandle(app_name="ap-test123", started_at=datetime.now(timezone.utc))
        config = ModalJobConfig(
            app_entrypoint="train.py",
            function_name="f",
            gpu_type=GPUType.T4,
            function_timeout_sec=60,
            max_wall_clock_sec=100,
        )

        finished_on_own = launcher.enforce_wall_clock_ceiling(
            handle,
            config,
            is_complete=lambda _h: False,
            poll_interval_sec=10.0,
            sleep_fn=lambda _s: None,
            clock=iter([0.0, 0.0, 50.0, 150.0]).__next__,
        )

        assert finished_on_own is False
        assert len(stop_calls) == 1

    def test_enforce_wall_clock_ceiling_returns_true_if_completes_first(self):
        launcher = ModalJobLauncher(runner=lambda args: _fake_result())
        from training.automation.modal_client import ModalJobHandle
        from datetime import datetime, timezone

        handle = ModalJobHandle(app_name="ap-test123", started_at=datetime.now(timezone.utc))
        config = ModalJobConfig(
            app_entrypoint="train.py", function_name="f", gpu_type=GPUType.T4,
            function_timeout_sec=60, max_wall_clock_sec=100,
        )

        result = launcher.enforce_wall_clock_ceiling(
            handle, config, is_complete=lambda _h: True, clock=lambda: 0.0,
        )
        assert result is True


# --------------------------------------------------------------------------
# Approval + Budget (CostGuard)
# --------------------------------------------------------------------------


class TestCostGuard:
    def test_authorize_paid_job_raises_when_no_approval_requested(self):
        guard = CostGuard(
            approval_store=InMemoryApprovalStore(),
            usage_ledger=InMemoryUsageLedger(),
            monthly_budget_usd=100.0,
        )
        with pytest.raises(ApprovalRequiredError):
            guard.authorize_paid_job("job-1", 10.0)

    def test_authorize_paid_job_raises_when_pending(self):
        approvals = InMemoryApprovalStore()
        from training.automation import ApprovalRecord

        approvals.request(ApprovalRecord(job_id="job-1", requested_by="agent", max_cost_usd=50.0))
        guard = CostGuard(approval_store=approvals, usage_ledger=InMemoryUsageLedger(), monthly_budget_usd=100.0)
        with pytest.raises(ApprovalRequiredError):
            guard.authorize_paid_job("job-1", 10.0)

    def test_authorize_paid_job_raises_when_rejected(self):
        approvals = InMemoryApprovalStore()
        from training.automation import ApprovalRecord

        approvals.request(ApprovalRecord(job_id="job-1", requested_by="agent", max_cost_usd=50.0))
        approvals.reject("job-1", approved_by="human", reason="not now")
        guard = CostGuard(approval_store=approvals, usage_ledger=InMemoryUsageLedger(), monthly_budget_usd=100.0)
        with pytest.raises(ApprovalRequiredError):
            guard.authorize_paid_job("job-1", 10.0)

    def test_authorize_paid_job_passes_when_approved_and_under_budget(self):
        approvals = InMemoryApprovalStore()
        from training.automation import ApprovalRecord

        approvals.request(ApprovalRecord(job_id="job-1", requested_by="agent", max_cost_usd=50.0))
        approvals.approve("job-1", approved_by="human")
        guard = CostGuard(approval_store=approvals, usage_ledger=InMemoryUsageLedger(), monthly_budget_usd=100.0)
        guard.authorize_paid_job("job-1", 10.0)  # must not raise

    def test_authorize_paid_job_raises_when_over_approved_ceiling(self):
        approvals = InMemoryApprovalStore()
        from training.automation import ApprovalRecord

        approvals.request(ApprovalRecord(job_id="job-1", requested_by="agent", max_cost_usd=5.0))
        approvals.approve("job-1", approved_by="human")
        guard = CostGuard(approval_store=approvals, usage_ledger=InMemoryUsageLedger(), monthly_budget_usd=100.0)
        with pytest.raises(ApprovalRequiredError, match="exceeds"):
            guard.authorize_paid_job("job-1", 10.0)

    def test_authorize_paid_job_raises_when_over_monthly_budget(self):
        approvals = InMemoryApprovalStore()
        from training.automation import ApprovalRecord

        approvals.request(ApprovalRecord(job_id="job-1", requested_by="agent", max_cost_usd=500.0))
        approvals.approve("job-1", approved_by="human")
        ledger = InMemoryUsageLedger()
        ledger.record(UsageRecord(
            job_id="prior", provider="runpod", amount_usd=90.0,
            incurred_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            period_key=UsageRecord.current_period_key(),
        ))
        guard = CostGuard(approval_store=approvals, usage_ledger=ledger, monthly_budget_usd=100.0)
        with pytest.raises(BudgetExceededError):
            guard.authorize_paid_job("job-1", 20.0)

    def test_record_actual_spend_and_remaining_budget(self):
        guard = CostGuard(
            approval_store=InMemoryApprovalStore(), usage_ledger=InMemoryUsageLedger(), monthly_budget_usd=100.0,
        )
        guard.record_actual_spend("job-1", provider="fal.ai", amount_usd=25.0)
        assert guard.remaining_budget_usd() == pytest.approx(75.0)

    def test_filesystem_approval_store_persists_across_instances(self, tmp_path):
        from training.automation import ApprovalRecord

        store_a = FilesystemApprovalStore(tmp_path)
        store_a.request(ApprovalRecord(job_id="job-1", requested_by="agent", max_cost_usd=20.0))
        store_a.approve("job-1", approved_by="human")

        store_b = FilesystemApprovalStore(tmp_path)
        record = store_b.get("job-1")
        assert record is not None
        assert record.status == ApprovalStatus.APPROVED
        assert record.approved_by == "human"

    def test_filesystem_usage_ledger_appends_and_sums(self, tmp_path):
        ledger_a = FilesystemUsageLedger(tmp_path)
        ledger_a.record(UsageRecord(
            job_id="j1", provider="runpod", amount_usd=12.5,
            incurred_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            period_key="2026-07",
        ))
        ledger_b = FilesystemUsageLedger(tmp_path)
        ledger_b.record(UsageRecord(
            job_id="j2", provider="fal.ai", amount_usd=4.0,
            incurred_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            period_key="2026-07",
        ))
        assert ledger_a.total_spent_in_period("2026-07") == pytest.approx(16.5)


# --------------------------------------------------------------------------
# ExperimentConfigGenerator + TrainingController
# --------------------------------------------------------------------------


class TestExperimentConfigGenerator:
    def test_generate_variant_within_range_succeeds(self):
        generator = ExperimentConfigGenerator(allowed_ranges={"learning_rate": (1e-6, 1e-3)})
        base = _base_training_config()
        variant = generator.generate_variant(base, {"learning_rate": 5e-5})
        assert variant.learning_rate == 5e-5
        assert variant.run_id == base.run_id  # unrelated fields untouched

    def test_generate_variant_outside_range_raises(self):
        generator = ExperimentConfigGenerator(allowed_ranges={"learning_rate": (1e-6, 1e-3)})
        base = _base_training_config()
        with pytest.raises(UnapprovedConfigOverrideError, match="outside the human-approved range"):
            generator.generate_variant(base, {"learning_rate": 1.0})

    def test_generate_variant_unlisted_field_raises(self):
        generator = ExperimentConfigGenerator(allowed_ranges={"learning_rate": (1e-6, 1e-3)})
        base = _base_training_config()
        with pytest.raises(UnapprovedConfigOverrideError, match="no configured allowed_range"):
            generator.generate_variant(base, {"max_train_steps": 5000})

    def test_generate_variant_still_runs_full_validation(self):
        base = _base_training_config()
        # batch_size=0 would be in no sane range, but prove validate() is still
        # the final authority even if a range were misconfigured to allow it.
        generator2 = ExperimentConfigGenerator(allowed_ranges={"batch_size": (0, 8)})
        with pytest.raises(ValueError, match="batch_size must be >= 1"):
            generator2.generate_variant(base, {"batch_size": 0})


class TestTrainingController:
    def _controller(self, *, cost_guard=None) -> TrainingController:
        return TrainingController(
            job_store=InMemoryJobStatusStore(),
            config_generator=ExperimentConfigGenerator(allowed_ranges={"learning_rate": (1e-6, 1e-3)}),
            cost_guard=cost_guard,
        )

    def test_plan_free_gpu_experiment_does_not_need_cost_guard(self):
        controller = self._controller()
        job = controller.plan_experiment(
            base_config=_base_training_config(),
            overrides={"learning_rate": 2e-5},
            tier=ExperimentTier.FREE_GPU,
            provider="kaggle",
        )
        assert job.status.value == "planned"
        assert job.tier == ExperimentTier.FREE_GPU

    def test_plan_paid_gpu_without_cost_guard_configured_raises(self):
        controller = self._controller(cost_guard=None)
        with pytest.raises(UnapprovedConfigOverrideError, match="no CostGuard configured"):
            controller.plan_experiment(
                base_config=_base_training_config(),
                overrides={},
                tier=ExperimentTier.PAID_GPU,
                provider="runpod",
                estimated_cost_usd=50.0,
            )

    def test_plan_paid_gpu_without_approval_raises(self):
        guard = CostGuard(
            approval_store=InMemoryApprovalStore(), usage_ledger=InMemoryUsageLedger(), monthly_budget_usd=1000.0,
        )
        controller = self._controller(cost_guard=guard)
        with pytest.raises(ApprovalRequiredError):
            controller.plan_experiment(
                base_config=_base_training_config(),
                overrides={},
                tier=ExperimentTier.PAID_GPU,
                provider="runpod",
                estimated_cost_usd=50.0,
                job_id="job-paid-1",
            )

    def test_plan_paid_gpu_with_approval_succeeds(self):
        approvals = InMemoryApprovalStore()
        from training.automation import ApprovalRecord

        approvals.request(ApprovalRecord(job_id="job-paid-1", requested_by="agent", max_cost_usd=100.0))
        approvals.approve("job-paid-1", approved_by="human")
        guard = CostGuard(approval_store=approvals, usage_ledger=InMemoryUsageLedger(), monthly_budget_usd=1000.0)
        controller = self._controller(cost_guard=guard)

        job = controller.plan_experiment(
            base_config=_base_training_config(),
            overrides={},
            tier=ExperimentTier.PAID_GPU,
            provider="runpod",
            estimated_cost_usd=50.0,
            job_id="job-paid-1",
        )
        assert job.job_id == "job-paid-1"

    def test_full_lifecycle_and_report(self):
        controller = self._controller()
        job = controller.plan_experiment(
            base_config=_base_training_config(),
            overrides={},
            tier=ExperimentTier.FREE_GPU,
            provider="modal",
            job_id="job-free-1",
        )
        controller.mark_started(job.job_id)
        controller.mark_completed(job.job_id, result_summary="Loss converged to 0.08")

        report = controller.report(job.job_id, quality_summary={"duration_conformance": "pass"})
        assert "job-free-1" in report
        assert "Loss converged to 0.08" in report
        assert "duration_conformance" in report

    def test_mark_completed_paid_job_records_actual_spend(self):
        approvals = InMemoryApprovalStore()
        from training.automation import ApprovalRecord

        approvals.request(ApprovalRecord(job_id="job-paid-2", requested_by="agent", max_cost_usd=100.0))
        approvals.approve("job-paid-2", approved_by="human")
        guard = CostGuard(approval_store=approvals, usage_ledger=InMemoryUsageLedger(), monthly_budget_usd=1000.0)
        controller = self._controller(cost_guard=guard)

        controller.plan_experiment(
            base_config=_base_training_config(), overrides={}, tier=ExperimentTier.PAID_GPU,
            provider="runpod", estimated_cost_usd=42.0, job_id="job-paid-2",
        )
        controller.mark_completed("job-paid-2", result_summary="done")

        assert guard.remaining_budget_usd() == pytest.approx(1000.0 - 42.0)

    def test_mark_failed_records_error(self):
        controller = self._controller()
        controller.plan_experiment(
            base_config=_base_training_config(), overrides={}, tier=ExperimentTier.FREE_CPU,
            provider="github-actions", job_id="job-cpu-1",
        )
        job = controller.mark_failed("job-cpu-1", error_message="dataset validation failed")
        assert job.status.value == "failed"
        assert job.error_message == "dataset validation failed"

    def test_report_unknown_job_raises(self):
        controller = self._controller()
        with pytest.raises(KeyError):
            controller.report("no-such-job")

    def test_filesystem_job_status_store_round_trips(self, tmp_path):
        store = FilesystemJobStatusStore(tmp_path)
        controller = TrainingController(
            job_store=store,
            config_generator=ExperimentConfigGenerator(allowed_ranges={}),
        )
        job = controller.plan_experiment(
            base_config=_base_training_config(), overrides={}, tier=ExperimentTier.FREE_CPU,
            provider="github-actions", job_id="job-fs-1",
        )
        store2 = FilesystemJobStatusStore(tmp_path)
        reloaded = store2.get("job-fs-1")
        assert reloaded is not None
        assert reloaded.config.run_id == job.config.run_id
        assert len(store2.list_all()) == 1

    def test_filesystem_job_status_store_accepts_a_plain_string_path(self, tmp_path):
        # Regression test: a real CI run (training-phase2-free-gpu-experiment.yml's
        # inline report-building script) passed a plain string, not a
        # pathlib.Path, and crashed with "'str' object has no attribute
        # 'mkdir'" - every existing caller/test happened to already pass a
        # real Path, so this was never caught until it hit CI for real.
        store = FilesystemJobStatusStore(str(tmp_path / "jobs"))
        assert (tmp_path / "jobs").is_dir()
        assert store.list_all() == []


def test_uses_real_base_model_registry_entry():
    # Sanity: the automation layer's config generator operates on the
    # exact same TrainingConfig/BASE_MODEL_REGISTRY built in Phase 9
    # Preparation, not a parallel/duplicated schema.
    assert "wan2.1" in BASE_MODEL_REGISTRY
    config = _base_training_config(base_model_id="wan2.1")
    config.validate()
