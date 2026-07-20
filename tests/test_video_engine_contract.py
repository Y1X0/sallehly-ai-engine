"""IVideoEngine contract tests: any adapter added to ADAPTERS_UNDER_TEST
must satisfy these invariants. This is the concrete template a future
custom Sallehly model (or any other engine) must pass - see
docs/adr/0001-director-engine-separation.md and
docs/adr/0009-generation-pipeline.md.
"""

from __future__ import annotations

import dataclasses

import pytest
import schemas
from video_engine_adapter.adapters import Wan21Adapter
from video_engine_sdk import EngineJobOutput, RenderSpec
from video_engine_sdk.types import CapabilityManifest, EngineJobPayload, RawClip

ADAPTERS_UNDER_TEST = [Wan21Adapter()]


def _sample_spec(mode: str = "text_to_video", conditioning_images: list[str] | None = None) -> RenderSpec:
    return RenderSpec(
        schema_version="1.0",
        shot_id="shot_test",
        duration_sec=3.0,
        fps=24,
        resolution="832x480",
        positive_prompt="a watch on a marble surface, golden hour lighting",
        negative_prompt="blurry, watermark",
        mode=mode,
        seed=42,
        motion_strength=50.0,
        conditioning_images=conditioning_images or [],
        quality_tier="final",
    )


@pytest.mark.parametrize("engine", ADAPTERS_UNDER_TEST, ids=lambda e: e.capabilities().engine_id)
def test_capabilities_returns_schema_valid_manifest(engine):
    capabilities = engine.capabilities()
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
    }
    if capabilities.license:
        manifest_dict["license"] = capabilities.license
    if capabilities.min_vram_gb:
        manifest_dict["gpu_requirements"] = {"min_vram_gb": capabilities.min_vram_gb}

    schemas.validate(manifest_dict, "capability_manifest")
    assert len(capabilities.modes) > 0
    assert len(capabilities.resolutions) > 0
    assert len(capabilities.fps_options) > 0


@pytest.mark.parametrize("engine", ADAPTERS_UNDER_TEST, ids=lambda e: e.capabilities().engine_id)
def test_build_job_payload_returns_valid_payload(engine):
    payload = engine.build_job_payload(_sample_spec())
    assert isinstance(payload, EngineJobPayload)
    assert payload.container_image
    assert isinstance(payload.input, dict)
    assert payload.resources.min_vram_gb > 0
    assert payload.resources.gpu_count >= 1


@pytest.mark.parametrize("engine", ADAPTERS_UNDER_TEST, ids=lambda e: e.capabilities().engine_id)
def test_build_job_payload_rejects_unsupported_mode(engine):
    with pytest.raises(ValueError, match="mode"):
        engine.build_job_payload(_sample_spec(mode="not_a_real_mode"))


@pytest.mark.parametrize("engine", ADAPTERS_UNDER_TEST, ids=lambda e: e.capabilities().engine_id)
def test_parse_result_returns_raw_clip(engine):
    spec = _sample_spec()
    output = EngineJobOutput(output_uri="file:///tmp/fake-clip.mp4", engine_metadata={"mock": True})

    raw_clip = engine.parse_result(spec, output)

    assert isinstance(raw_clip, RawClip)
    assert raw_clip.shot_id == spec.shot_id
    assert raw_clip.storage_uri == output.output_uri
    assert raw_clip.duration_sec == spec.duration_sec


def test_wan21_image_to_video_maps_conditioning_image_to_native_key():
    engine = Wan21Adapter()
    spec = _sample_spec(mode="image_to_video", conditioning_images=["asset://ref-image-1"])

    payload = engine.build_job_payload(spec)

    assert payload.input["image"] == "asset://ref-image-1"
    assert "conditioning_images" not in payload.input


def test_wan21_omits_seed_key_when_unset():
    engine = Wan21Adapter()
    spec_no_seed = dataclasses.replace(_sample_spec(), seed=None)

    payload = engine.build_job_payload(spec_no_seed)

    assert "seed" not in payload.input


def test_wan21_includes_seed_when_set():
    engine = Wan21Adapter()
    payload = engine.build_job_payload(_sample_spec())
    assert payload.input["seed"] == 42


def test_register_defaults_wires_config_sdk_registries():
    import video_engine_adapter
    from config_sdk import COMPUTE_PROVIDER_REGISTRY, VIDEO_ENGINE_REGISTRY

    video_engine_adapter.register_defaults()  # safe to call more than once

    assert "wan2.1" in VIDEO_ENGINE_REGISTRY
    assert "local" in COMPUTE_PROVIDER_REGISTRY
    assert "runpod" in COMPUTE_PROVIDER_REGISTRY
    assert "vastai" in COMPUTE_PROVIDER_REGISTRY

    assert isinstance(VIDEO_ENGINE_REGISTRY.create("wan2.1"), Wan21Adapter)

    from video_engine_adapter.compute import LocalProvider

    assert isinstance(COMPUTE_PROVIDER_REGISTRY.create("local"), LocalProvider)
