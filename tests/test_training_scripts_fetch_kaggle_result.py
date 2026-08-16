"""Tests for services/training/scripts/fetch_kaggle_kernel_result.py -
real KaggleClient.poll_kernel_until_terminal()/pull_kernel_output(),
with an injected fake subprocess runner (no network, no real Kaggle CLI).
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "services" / "training" / "scripts" / "fetch_kaggle_kernel_result.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("fetch_kaggle_kernel_result_under_test", _SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fake_result(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


class TestFetchKaggleKernelResult:
    def test_rejects_malformed_kernel_ref(self, capsys):
        module = _load_module()

        exit_code = module.main(["--kernel-ref", "not-a-valid-ref", "--output-dir", "/tmp/out"])

        assert exit_code == 1
        assert "owner_slug/kernel_slug" in capsys.readouterr().err

    def test_polls_until_complete_and_pulls_output(self, tmp_path, monkeypatch):
        module = _load_module()
        calls: list[list[str]] = []

        def fake_runner(args: list[str]) -> subprocess.CompletedProcess:
            calls.append(args)
            if "status" in args:
                return _fake_result(stdout='Kernel is currently "complete"')
            return _fake_result(stdout="output pulled")

        real_kaggle_client_cls = module.KaggleClient
        monkeypatch.setattr(module, "KaggleClient", lambda: real_kaggle_client_cls(runner=fake_runner))

        exit_code = module.main([
            "--kernel-ref", "me/my-kernel", "--output-dir", str(tmp_path / "out"), "--poll-interval-sec", "0",
        ])

        assert exit_code == 0
        assert any("status" in call for call in calls)
        assert any("output" in call for call in calls)

    def test_returns_nonzero_when_kernel_errors(self, tmp_path, monkeypatch):
        module = _load_module()

        def fake_runner(args: list[str]) -> subprocess.CompletedProcess:
            if "status" in args:
                return _fake_result(stdout='Kernel is currently "error"')
            return _fake_result(stdout="output pulled")

        real_kaggle_client_cls = module.KaggleClient
        monkeypatch.setattr(module, "KaggleClient", lambda: real_kaggle_client_cls(runner=fake_runner))

        exit_code = module.main([
            "--kernel-ref", "me/my-kernel", "--output-dir", str(tmp_path / "out"), "--poll-interval-sec", "0",
        ])

        assert exit_code == 1

    def test_prints_the_real_failure_message_when_kernel_errors(self, tmp_path, monkeypatch, capsys):
        # `kaggle kernels status` prints a real "Failure message: ..." line
        # for an errored kernel - printing it straight to this script's own
        # stdout means the actual cause is visible in a CI job log, without
        # a separate step to download/inspect kernel output files.
        module = _load_module()
        raw_status = 'me/my-kernel has status "error"\nFailure message: "Traceback: ImportError: no module named foo"\n'

        def fake_runner(args: list[str]) -> subprocess.CompletedProcess:
            if "status" in args:
                return _fake_result(stdout=raw_status)
            return _fake_result(stdout="output pulled")

        real_kaggle_client_cls = module.KaggleClient
        monkeypatch.setattr(module, "KaggleClient", lambda: real_kaggle_client_cls(runner=fake_runner))

        exit_code = module.main([
            "--kernel-ref", "me/my-kernel", "--output-dir", str(tmp_path / "out"), "--poll-interval-sec", "0",
        ])

        assert exit_code == 1
        assert "ImportError: no module named foo" in capsys.readouterr().out

    def test_timeout_still_pulls_output(self, tmp_path, monkeypatch):
        # Fix: a polling timeout must not throw away whatever logs/
        # checkpoints the kernel had already produced - pull_kernel_output
        # must still be attempted.
        module = _load_module()
        calls: list[list[str]] = []

        def fake_runner(args: list[str]) -> subprocess.CompletedProcess:
            calls.append(args)
            if "status" in args:
                return _fake_result(stdout='Kernel is currently "running"')
            return _fake_result(stdout="output pulled")

        real_kaggle_client_cls = module.KaggleClient
        monkeypatch.setattr(module, "KaggleClient", lambda: real_kaggle_client_cls(runner=fake_runner))

        exit_code = module.main([
            "--kernel-ref", "me/my-kernel", "--output-dir", str(tmp_path / "out"),
            "--poll-interval-sec", "0", "--timeout-sec", "0",
        ])

        assert exit_code == 1
        assert any("output" in call for call in calls)

    def test_validate_checkpoint_passes_with_a_real_loadable_adapter(self, tmp_path, monkeypatch):
        torch = pytest.importorskip("torch")
        from safetensors.torch import save_file

        module = _load_module()
        output_dir = tmp_path / "out"
        adapter_dir = output_dir / "adapters" / "unified" / "step_000010"
        adapter_dir.mkdir(parents=True)
        save_file({"lora_A.weight": torch.zeros(2, 2)}, str(adapter_dir / "adapter_model.safetensors"))

        def fake_runner(args: list[str]) -> subprocess.CompletedProcess:
            if "status" in args:
                return _fake_result(stdout='Kernel is currently "complete"')
            return _fake_result(stdout="output pulled")

        real_kaggle_client_cls = module.KaggleClient
        monkeypatch.setattr(module, "KaggleClient", lambda: real_kaggle_client_cls(runner=fake_runner))

        exit_code = module.main([
            "--kernel-ref", "me/my-kernel", "--output-dir", str(output_dir),
            "--poll-interval-sec", "0", "--validate-checkpoint",
        ])

        assert exit_code == 0

    def test_validate_checkpoint_fails_when_no_adapter_was_produced(self, tmp_path, monkeypatch):
        module = _load_module()

        def fake_runner(args: list[str]) -> subprocess.CompletedProcess:
            if "status" in args:
                return _fake_result(stdout='Kernel is currently "complete"')
            return _fake_result(stdout="output pulled")

        real_kaggle_client_cls = module.KaggleClient
        monkeypatch.setattr(module, "KaggleClient", lambda: real_kaggle_client_cls(runner=fake_runner))

        exit_code = module.main([
            "--kernel-ref", "me/my-kernel", "--output-dir", str(tmp_path / "out"),
            "--poll-interval-sec", "0", "--validate-checkpoint",
        ])

        assert exit_code == 1
