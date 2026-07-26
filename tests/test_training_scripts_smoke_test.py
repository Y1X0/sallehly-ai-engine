"""Tests for services/training/scripts/run_smoke_test.py - the
controlled, zero-cost smoke test required before any real GPU run
(docs/EXECUTION_PLAN_FIRST_GPU_RUN.md). Requires the training[gpu-training]
extra; skipped entirely when it is not installed.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("torch")
pytest.importorskip("diffusers")
pytest.importorskip("peft")

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "services" / "training" / "scripts" / "run_smoke_test.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_smoke_test_under_test", _SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestRunSmokeTest:
    @pytest.mark.parametrize("base_model_id", ["wan2.2-ti2v-5b", "wan2.2-t2v-a14b", "wan2.2-i2v-a14b"])
    def test_smoke_test_passes_for_every_wan22_variant(self, base_model_id):
        module = _load_module()

        exit_code = module.main(["--base-model-id", base_model_id, "--max-train-steps", "4"])

        assert exit_code == 0

    def test_keep_workdir_leaves_directory_on_disk(self, capsys):
        module = _load_module()

        exit_code = module.main(["--max-train-steps", "2", "--keep-workdir"])

        assert exit_code == 0
        output = capsys.readouterr().out
        assert "Kept working directory:" in output
        workdir_line = next(line for line in output.splitlines() if line.startswith("Kept working directory:"))
        workdir = Path(workdir_line.split(": ", 1)[1])
        assert workdir.is_dir()
        import shutil

        shutil.rmtree(workdir, ignore_errors=True)
