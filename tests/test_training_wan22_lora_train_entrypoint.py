"""Tests for services/training/entrypoints/wan22_lora_train.py's own
fixes from the pre-first-real-run production audit:

- `_resolve_device` (fix #1): CUDA auto-detection that fails immediately
  rather than silently falling back to CPU - --device previously
  defaulted to "cpu" with no enforcement at all.
- `_build_backend` (fix #2): TrainingConfig.seed is now threaded through
  to both the smoke-test and real backends, previously dropped
  entirely.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

torch = pytest.importorskip("torch")

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "services" / "training" / "entrypoints" / "wan22_lora_train.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("wan22_lora_train_under_test", _SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestResolveDevice:
    def test_cpu_is_always_allowed_even_without_torch_installed_state(self):
        module = _load_module()
        assert module._resolve_device("cpu") == "cpu"

    def test_auto_raises_without_cuda(self, monkeypatch):
        module = _load_module()
        monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
        with pytest.raises(RuntimeError, match="CUDA"):
            module._resolve_device("auto")

    def test_cuda_raises_without_cuda(self, monkeypatch):
        module = _load_module()
        monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
        with pytest.raises(RuntimeError, match="CUDA"):
            module._resolve_device("cuda")

    def test_auto_resolves_to_cuda_when_available(self, monkeypatch):
        module = _load_module()
        monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
        assert module._resolve_device("auto") == "cuda"


class TestBuildBackendSeeding:
    def test_smoke_test_backend_receives_configured_seed(self):
        module = _load_module()
        args = SimpleNamespace(
            backend="smoke-test", device="cpu",
            registry="models/registry.yaml", models_cache_root=".models-cache",
        )
        backend = module._build_backend(args, "wan2.2-ti2v-5b", 1e-4, 123)
        assert backend._batch_encoder._seed == 123

    def test_real_backend_path_enforces_cuda_before_ever_touching_weights(self, monkeypatch, tmp_path):
        # Reproduces the exact bug this fix closes: a real Kaggle GPU
        # dispatch reaching the real-backend path with no CUDA actually
        # available must fail immediately, not silently train on CPU.
        module = _load_module()
        monkeypatch.setattr(torch.cuda, "is_available", lambda: False)

        fake_manifest = SimpleNamespace(local_dir=str(tmp_path), verify=lambda: None)
        monkeypatch.setattr(module, "resolve_local_weights", lambda base_model_id, cache_root: fake_manifest)
        fake_entry = SimpleNamespace(experts={"unified": "transformer"})
        monkeypatch.setattr(module, "load_wan22_registry_entries", lambda registry: {"wan2.2-ti2v-5b": fake_entry})

        args = SimpleNamespace(
            backend="real", device="auto",
            registry="models/registry.yaml", models_cache_root=".models-cache",
        )
        with pytest.raises(RuntimeError, match="CUDA"):
            module._build_backend(args, "wan2.2-ti2v-5b", 1e-4, 0)
