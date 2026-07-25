from __future__ import annotations


class ModelUnavailableError(Exception):
    """Raised by every model adapter method that needs an optional ML
    dependency and/or downloaded model weights this process doesn't
    have. Every adapter in this package lazily imports its real
    dependency inside the method that needs it (never at module import
    time), so importing `cinematic_intelligence.model_adapters` never
    fails even when none of torch/open_clip/controlnet_aux/transformers
    are installed - only *calling* an adapter without its dependency
    installed does, with an actionable message (what to `pip install`).
    This is the same "prepared, not implemented" honesty standard as
    `PassthroughUpscaler` (ADR 0012) and `SallehlyModelAdapter` (ADR
    0014): real integration code, no GPU/model weights in this sandbox
    to actually run it. See docs/adr/0014-pipeline-integration.md.
    """
