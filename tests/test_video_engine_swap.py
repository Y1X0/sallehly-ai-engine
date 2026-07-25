"""Phase 8 video engine swappability (ADR 0014): VIDEO_ENGINE_REGISTRY +
Settings.video_engine let apps/api pick between Wan2.1 and the new
SallehlyModelAdapter (a second real IVideoEngine implementation) purely
through config - GenerationPipeline, RenderConfigCompiler, and
ProjectLifecycle never import a concrete engine directly. This also
covers the real gap found and fixed this phase: apps/api/state.py used
to hardcode Wan21Adapter() and never actually read
VIDEO_ENGINE_REGISTRY/Settings.video_engine at all.
"""

from __future__ import annotations

import pytest
import schemas
from api.state import build_app_state
from config_sdk import VIDEO_ENGINE_REGISTRY, Settings
from conftest import SAMPLE_BRIEF
from persistence import ProjectStatus
from video_engine_adapter import register_defaults
from video_engine_adapter.adapters import SallehlyModelAdapter, SallehlyModelNotTrainedError, Wan21Adapter
from video_engine_sdk.types import CapabilityManifest


def test_register_defaults_registers_both_engines():
    register_defaults()  # safe to call more than once
    assert "wan2.1" in VIDEO_ENGINE_REGISTRY
    assert "sallehly-v1" in VIDEO_ENGINE_REGISTRY
    assert isinstance(VIDEO_ENGINE_REGISTRY.create("wan2.1"), Wan21Adapter)
    assert isinstance(VIDEO_ENGINE_REGISTRY.create("sallehly-v1"), SallehlyModelAdapter)


def test_sallehly_model_adapter_capabilities_is_a_real_schema_valid_manifest():
    capabilities = SallehlyModelAdapter().capabilities()
    assert isinstance(capabilities, CapabilityManifest)

    manifest_dict = {
        "engine_id": capabilities.engine_id,
        "engine_version": capabilities.engine_version,
        "modes": capabilities.modes,
        "max_shot_duration_sec": capabilities.max_shot_duration_sec,
        "min_shot_duration_sec": capabilities.min_shot_duration_sec,
        "resolutions": capabilities.resolutions,
        "fps_options": capabilities.fps_options,
        "motion_strength_range": list(capabilities.motion_strength_range),
        "supports_negative_prompt": capabilities.supports_negative_prompt,
        "supports_seed": capabilities.supports_seed,
        "supports_conditioning_images": capabilities.supports_conditioning_images,
        "max_conditioning_images": capabilities.max_conditioning_images,
        "license": capabilities.license,
    }
    schemas.validate(manifest_dict, "capability_manifest")
    assert capabilities.engine_id == "sallehly-v1"


def test_sallehly_model_adapter_build_job_payload_raises_not_trained():
    from video_engine_sdk import RenderSpec

    spec = RenderSpec(
        schema_version="1.0",
        shot_id="shot_1",
        duration_sec=2.0,
        fps=24,
        resolution="1280x720",
        positive_prompt="a watch on marble",
        negative_prompt="blurry",
        mode="text_to_video",
    )
    with pytest.raises(SallehlyModelNotTrainedError, match="no trained weights"):
        SallehlyModelAdapter().build_job_payload(spec)


def test_sallehly_model_adapter_parse_result_raises_not_trained():
    from video_engine_sdk import EngineJobOutput, RenderSpec

    spec = RenderSpec(
        schema_version="1.0",
        shot_id="shot_1",
        duration_sec=2.0,
        fps=24,
        resolution="1280x720",
        positive_prompt="a watch on marble",
        negative_prompt="blurry",
        mode="text_to_video",
    )
    output = EngineJobOutput(output_uri="file:///tmp/x.mp4", engine_metadata={})
    with pytest.raises(SallehlyModelNotTrainedError, match="no trained weights"):
        SallehlyModelAdapter().parse_result(spec, output)


def test_build_app_state_defaults_to_wan21_and_completes_generation():
    state = build_app_state(Settings())
    record = state.orchestrator.create_project(**SAMPLE_BRIEF)
    state.orchestrator.generate_creative_plan(record.project_id)
    state.orchestrator.approve_storyboard(record.project_id)
    state.orchestrator.approve_render_plan(record.project_id)

    record = state.orchestrator.generate_video(record.project_id)

    assert record.status == ProjectStatus.COMPLETED


def test_build_app_state_swaps_to_sallehly_engine_via_settings_with_zero_pipeline_changes():
    # The point of this test: nothing about build_app_state's call sites
    # (create_project/generate_creative_plan/approve_storyboard/
    # approve_render_plan/generate_video) changes between this test and
    # the wan2.1 test above - only the Settings value passed in differs.
    # ProjectLifecycle/GenerationPipeline/RenderConfigCompiler never know
    # which concrete IVideoEngine they were handed.
    state = build_app_state(Settings(video_engine="sallehly-v1"))
    record = state.orchestrator.create_project(**SAMPLE_BRIEF)
    state.orchestrator.generate_creative_plan(record.project_id)
    state.orchestrator.approve_storyboard(record.project_id)
    state.orchestrator.approve_render_plan(record.project_id)

    record = state.orchestrator.generate_video(record.project_id)

    assert record.status == ProjectStatus.FAILED
    assert "no trained weights" in record.error_message
