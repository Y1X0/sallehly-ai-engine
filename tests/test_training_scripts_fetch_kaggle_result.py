"""Tests for services/training/scripts/fetch_kaggle_kernel_result.py -
real KaggleClient.poll_kernel_until_terminal()/pull_kernel_output(),
with an injected fake subprocess runner (no network, no real Kaggle CLI).
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

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
