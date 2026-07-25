from __future__ import annotations

from ..errors import ModelUnavailableError
from .interfaces import ICaptionProvider
from .records import ClipRecord


class HeuristicCaptionProvider(ICaptionProvider):
    """Real, deterministic, metadata-derived caption - no VLM, always
    available. Deliberately coarse: this exists so every clip has a
    non-empty, schema-shaped caption today, letting the rest of the
    pipeline (validation, statistics, training-config wiring) be
    exercised end-to-end before Stage 4 of the Phase 9 roadmap
    (docs/adr/0021-phase9-preparation.md) replaces it with a real
    vision-language model pass. Caller-supplied `tags` (set at ingest
    time, e.g. "product-shot", "handheld") are the only real per-clip
    semantic content available without a real captioning model."""

    def generate_caption(self, record: ClipRecord) -> str:
        parts: list[str] = []
        if record.tags:
            parts.append(", ".join(record.tags))
        parts.append(f"{record.metadata.resolution} at {record.metadata.fps:g}fps")
        parts.append(f"{record.metadata.duration_sec:.1f}s clip")
        return ", ".join(parts)


class VLMCaptionProvider(ICaptionProvider):
    """The real Stage 4 integration point - a vision-language model
    producing dense, `RenderSpec.positive_prompt`-shaped captions
    (camera/lighting/motion/style descriptors), not just metadata.
    Raises `ModelUnavailableError` unconditionally today: no VLM
    dependency is installed and no weights exist in this environment,
    the same honesty posture as
    `cinematic_intelligence.model_adapters.embedding_providers.ClipEmbeddingProvider`.
    """

    def __init__(self, model_name: str = "placeholder-vlm") -> None:
        self._model_name = model_name

    def generate_caption(self, record: ClipRecord) -> str:
        raise ModelUnavailableError(
            f"VLMCaptionProvider(model_name={self._model_name!r}) needs a real "
            "vision-language model and weights - none are installed in this environment. "
            "Use HeuristicCaptionProvider until Stage 4 of the Phase 9 roadmap wires in "
            "a real captioning model."
        )
