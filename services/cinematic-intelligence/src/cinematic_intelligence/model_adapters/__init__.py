from __future__ import annotations

from config_sdk import CONDITIONING_ADAPTER_REGISTRY, EMBEDDING_PROVIDER_REGISTRY

from .conditioning_adapters import ControlNetConditioningAdapter, IPAdapterConditioningAdapter
from .embedding_providers import ClipEmbeddingProvider, DinoEmbeddingProvider
from .errors import ModelUnavailableError

__all__ = [
    "ClipEmbeddingProvider",
    "ControlNetConditioningAdapter",
    "DinoEmbeddingProvider",
    "IPAdapterConditioningAdapter",
    "ModelUnavailableError",
    "register_defaults",
]


def register_defaults() -> None:
    """Registers every built-in model adapter into
    EMBEDDING_PROVIDER_REGISTRY/CONDITIONING_ADAPTER_REGISTRY, keyed by
    provider id. Idempotent. Registering an adapter costs nothing (no
    import of torch/transformers/controlnet_aux happens here - see each
    adapter's lazy `_ensure_loaded`/`apply`) - only *using* one does."""
    EMBEDDING_PROVIDER_REGISTRY.register_if_absent("clip", ClipEmbeddingProvider)
    EMBEDDING_PROVIDER_REGISTRY.register_if_absent("dino", DinoEmbeddingProvider)
    CONDITIONING_ADAPTER_REGISTRY.register_if_absent("controlnet", ControlNetConditioningAdapter)
    CONDITIONING_ADAPTER_REGISTRY.register_if_absent("ip_adapter", IPAdapterConditioningAdapter)
