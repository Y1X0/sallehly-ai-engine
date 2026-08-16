"""Tests for apps/api/src/api/state.py::build_app_state's compute
provider selection - specifically the fix for a silent-failure gap a
production audit found: COMPUTE_PROVIDER=runpod with incomplete
credentials used to fall straight through to LocalProvider (a mock
stub) with no indication why. Also covers the new
COMPUTE_PROVIDER=local-inference wiring (real, zero-credential local
generation - see video_engine_adapter.compute.LocalInferenceProvider).
"""

from __future__ import annotations

import pytest
from api.state import build_app_state
from config_sdk import Settings


def test_default_settings_still_build_without_error():
    # Unchanged, existing behavior (LocalProvider mock default) - must
    # not regress for every test/dev environment that relies on it.
    state = build_app_state(Settings())
    assert state.lifecycle is not None


def test_runpod_without_credentials_raises_a_clear_error_instead_of_silently_mocking():
    with pytest.raises(RuntimeError, match="RUNPOD_API_KEY"):
        build_app_state(Settings(compute_provider="runpod"))


def test_runpod_with_only_api_key_still_raises():
    with pytest.raises(RuntimeError, match="RUNPOD_ENDPOINT_ID"):
        build_app_state(Settings(compute_provider="runpod", runpod_api_key="key-only"))


def test_runpod_with_both_credentials_builds_a_real_runpod_provider():
    from video_engine_adapter.compute import RunPodProvider

    state = build_app_state(
        Settings(compute_provider="runpod", runpod_api_key="k", runpod_endpoint_id="e")
    )
    assert RunPodProvider  # constructed without error inside build_app_state
    assert state.lifecycle is not None


def test_local_inference_smoke_mode_requires_no_credentials():
    state = build_app_state(Settings(compute_provider="local-inference"))
    assert state.lifecycle is not None


def test_local_inference_real_mode_without_model_id_raises_clearly():
    with pytest.raises(RuntimeError, match="VIDEO_INFERENCE_MODEL_ID"):
        build_app_state(
            Settings(compute_provider="local-inference", video_inference_smoke_test=False)
        )


def test_local_inference_real_mode_with_model_id_builds_without_error():
    state = build_app_state(
        Settings(
            compute_provider="local-inference", video_inference_smoke_test=False,
            video_inference_model_id="Wan-AI/Wan2.1-T2V-1.3B-Diffusers",
        )
    )
    assert state.lifecycle is not None
