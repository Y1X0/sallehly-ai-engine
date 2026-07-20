from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


@dataclass(frozen=True)
class CapabilityManifest:
    """Mirrors packages/schemas/json/capability_manifest.schema.json.

    Loaded from models/<engine_id>/capability_manifest.yaml by the Model
    Registry and handed to the Render Configuration Compiler, which is the
    only caller that needs it before an adapter is even involved.
    """

    engine_id: str
    engine_version: str
    modes: list[str]
    max_shot_duration_sec: float
    min_shot_duration_sec: float
    resolutions: list[str]
    fps_options: list[int]
    motion_strength_range: tuple[float, float] = (0.0, 100.0)
    supports_negative_prompt: bool = True
    supports_seed: bool = True
    supports_conditioning_images: bool = False
    max_conditioning_images: int = 0
    license: str | None = None
    min_vram_gb: float | None = None


@dataclass(frozen=True)
class RenderSpec:
    """Mirrors packages/schemas/json/render_configuration.schema.json.

    This is the ONLY input a Video Engine Adapter is allowed to require.
    It must never grow a field that only one engine understands - if an
    engine needs extra knobs, they live in that adapter's own
    engine-specific config, not here.
    """

    schema_version: str
    shot_id: str
    duration_sec: float
    fps: int
    resolution: str
    positive_prompt: str
    aspect_ratio: str | None = None
    mode: str = "text_to_video"
    negative_prompt: str | None = None
    seed: int | None = None
    motion_strength: float | None = None
    camera: dict[str, Any] | None = None
    lighting: dict[str, Any] | None = None
    conditioning_images: list[str] = field(default_factory=list)
    engine_id: str | None = None
    quality_tier: str = "final"


@dataclass(frozen=True)
class ComputeResourceRequirements:
    min_vram_gb: float
    gpu_count: int = 1
    timeout_sec: int = 900


@dataclass(frozen=True)
class EngineJobPayload:
    """What an IVideoEngine hands to an IComputeProvider to actually run.

    container_image + input together fully describe one unit of GPU work.
    The compute provider does not need to understand `input` - it only
    needs to get it onto the container and back.
    """

    container_image: str
    input: dict[str, Any]
    resources: ComputeResourceRequirements


class ComputeJobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class ComputeJobHandle:
    provider_id: str
    external_job_id: str


@dataclass(frozen=True)
class EngineJobOutput:
    output_uri: str
    engine_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RawClip:
    shot_id: str
    storage_uri: str
    duration_sec: float
    resolution: str
    engine_metadata: dict[str, Any] = field(default_factory=dict)
