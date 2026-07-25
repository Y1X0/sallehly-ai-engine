from __future__ import annotations

from video_engine_sdk import (
    CapabilityManifest,
    EngineJobOutput,
    EngineJobPayload,
    IVideoEngine,
    RawClip,
    RenderSpec,
)


class SallehlyModelNotTrainedError(Exception):
    """Raised by every method that would need real model weights to
    execute. `services/training` (Phase 9 - "Custom foundation model
    track", see docs/ARCHITECTURE.md roadmap) has not produced any
    weights - this adapter exists to prove `IVideoEngine` is a real
    swap point (config-driven, zero code changes upstream), not to
    generate video."""


class SallehlyModelAdapter(IVideoEngine):
    """The second `IVideoEngine` implementation, proving
    `VIDEO_ENGINE_REGISTRY`/`Settings.video_engine` genuinely swap the
    active engine without touching `GenerationPipeline`, `RenderConfigCompiler`,
    or anything above them - exactly the guarantee ADR 0001/0002 exist to
    provide. `capabilities()` is real, declarative metadata for the
    custom foundation model this project intends to train eventually
    (Phase 9); `build_job_payload`/`parse_result` are correct in shape
    (same method signatures, same RenderSpec input, same RawClip output
    every other adapter honors) but raise `SallehlyModelNotTrainedError`
    rather than fabricating a container image or a fake result, because
    no weights exist to run. See docs/adr/0014-pipeline-integration.md.

    Select it via `VIDEO_ENGINE=sallehly-v1` (`.env`/`Settings.video_engine`)
    - `apps/api/state.py` reads that value through `VIDEO_ENGINE_REGISTRY`,
    the same way it already does for `wan2.1`.
    """

    def capabilities(self) -> CapabilityManifest:
        return CapabilityManifest(
            engine_id="sallehly-v1",
            engine_version="0.0.0-unreleased",
            modes=["text_to_video", "image_to_video"],
            max_shot_duration_sec=8.0,
            min_shot_duration_sec=1.0,
            resolutions=["1280x720", "1920x1080"],
            fps_options=[24, 30],
            motion_strength_range=(0.0, 100.0),
            supports_negative_prompt=True,
            supports_seed=True,
            supports_conditioning_images=True,
            max_conditioning_images=4,
            license="proprietary",
            min_vram_gb=None,
        )

    def build_job_payload(self, spec: RenderSpec) -> EngineJobPayload:
        raise SallehlyModelNotTrainedError(
            "SallehlyModelAdapter has no trained weights or container image yet "
            "(services/training is Phase 9, not started) - this method's signature "
            "and CapabilityManifest are real and IComputeProvider-compatible; only "
            "the actual GPU inference call is unimplemented, the same class of "
            "limitation as Wan2.1 inference in an environment with no GPU."
        )

    def parse_result(self, spec: RenderSpec, output: EngineJobOutput) -> RawClip:
        raise SallehlyModelNotTrainedError(
            "SallehlyModelAdapter has no trained weights yet - there is no real "
            "EngineJobOutput to parse."
        )
