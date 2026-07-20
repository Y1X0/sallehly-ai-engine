from __future__ import annotations

from config_sdk import COMPUTE_PROVIDER_REGISTRY, VIDEO_ENGINE_REGISTRY

from .adapters import Wan21Adapter
from .compute import LocalProvider, RunPodProvider, VastAIProvider


def register_defaults() -> None:
    """Registers every engine/compute-provider this package ships into
    config_sdk's shared registries, so the rest of the system can select
    one purely by the VIDEO_ENGINE/COMPUTE_PROVIDER config strings (see
    .env.example) instead of importing a concrete class directly.

    Safe to call more than once (e.g. multiple entrypoints importing this
    module within the same process) - uses register_if_absent.
    """
    VIDEO_ENGINE_REGISTRY.register_if_absent("wan2.1", Wan21Adapter)

    COMPUTE_PROVIDER_REGISTRY.register_if_absent("local", LocalProvider)
    COMPUTE_PROVIDER_REGISTRY.register_if_absent("runpod", RunPodProvider)
    COMPUTE_PROVIDER_REGISTRY.register_if_absent("vastai", VastAIProvider)
