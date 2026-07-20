from __future__ import annotations

from video_engine_sdk import (
    CapabilityManifest,
    ComputeResourceRequirements,
    EngineJobOutput,
    EngineJobPayload,
    IVideoEngine,
    RawClip,
    RenderSpec,
)

WAN21_CONTAINER_IMAGE = "sallehly/wan21-worker:2.1.0"

# Wan2.1-specific generation defaults - these are NOT RenderSpec fields
# (per ADR 0001, engine-specific knobs never belong in the shared schema)
# and are hardcoded here rather than exposed upstream.
_DEFAULT_GUIDANCE_SCALE = 6.0
_SAMPLING_STEPS = {"final": 40, "standard": 25, "preview": 15}


class Wan21Adapter(IVideoEngine):
    """First IVideoEngine implementation, wrapping the open-source Wan2.1
    text/image-to-video pipeline (Apache-2.0, see models/wan2.1/).

    See docs/adapters/wan21-adapter-spec.md for the full mapping between
    RenderSpec fields and Wan2.1's native inference arguments - this class
    is the executable counterpart of that spec and must be kept in sync
    with it.
    """

    def capabilities(self) -> CapabilityManifest:
        return CapabilityManifest(
            engine_id="wan2.1",
            engine_version="2.1.0",
            modes=["text_to_video", "image_to_video", "video_edit"],
            max_shot_duration_sec=5.0,
            min_shot_duration_sec=1.0,
            resolutions=["832x480", "1280x720"],
            fps_options=[16, 24],
            motion_strength_range=(0.0, 100.0),
            supports_negative_prompt=True,
            supports_seed=True,
            supports_conditioning_images=True,
            max_conditioning_images=1,
            license="Apache-2.0",
            min_vram_gb=24.0,
        )

    def build_job_payload(self, spec: RenderSpec) -> EngineJobPayload:
        capabilities = self.capabilities()
        if spec.mode not in capabilities.modes:
            raise ValueError(
                f"Wan21Adapter received mode={spec.mode!r}, which its own CapabilityManifest "
                f"does not list ({capabilities.modes}). The Render Configuration Compiler should "
                "never produce a RenderSpec whose mode the active engine doesn't support."
            )

        width, height = (int(dim) for dim in spec.resolution.split("x"))
        num_frames = round(spec.duration_sec * spec.fps)

        wan21_input: dict[str, object] = {
            "task": self._map_mode(spec.mode),
            "prompt": spec.positive_prompt,
            "negative_prompt": spec.negative_prompt or "",
            "width": width,
            "height": height,
            "num_frames": num_frames,
            "fps": spec.fps,
            "motion_strength": spec.motion_strength,
            "guidance_scale": _DEFAULT_GUIDANCE_SCALE,
            "sampling_steps": _SAMPLING_STEPS.get(spec.quality_tier, _SAMPLING_STEPS["final"]),
        }

        # Wan2.1 does not accept a null seed - omit it entirely and let the
        # worker generate one, rather than sending seed=None.
        if spec.seed is not None:
            wan21_input["seed"] = spec.seed

        # image_to_video wants a single conditioning image under its own
        # native key; video_edit may use multiple. text_to_video sends none.
        if spec.mode == "image_to_video" and spec.conditioning_images:
            wan21_input["image"] = spec.conditioning_images[0]
        elif spec.mode == "video_edit" and spec.conditioning_images:
            wan21_input["reference_images"] = list(spec.conditioning_images)

        return EngineJobPayload(
            container_image=WAN21_CONTAINER_IMAGE,
            input=wan21_input,
            resources=ComputeResourceRequirements(
                min_vram_gb=capabilities.min_vram_gb or 24.0,
                gpu_count=1,
                timeout_sec=900,
            ),
        )

    def parse_result(self, spec: RenderSpec, output: EngineJobOutput) -> RawClip:
        return RawClip(
            shot_id=spec.shot_id,
            storage_uri=output.output_uri,
            duration_sec=spec.duration_sec,
            resolution=spec.resolution,
            engine_metadata=output.engine_metadata,
        )

    @staticmethod
    def _map_mode(mode: str) -> str:
        return {
            "text_to_video": "t2v",
            "image_to_video": "i2v",
            "video_edit": "v2v",
        }[mode]
