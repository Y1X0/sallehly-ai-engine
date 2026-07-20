from __future__ import annotations

from abc import ABC, abstractmethod

from .types import CapabilityManifest, EngineJobOutput, EngineJobPayload, RawClip, RenderSpec


class IVideoEngine(ABC):
    """The engine-agnostic execution contract.

    Defines WHICH MODEL runs and how to talk to it - never WHERE it runs
    (that is IComputeProvider's job, see compute_base.py). Wan21Adapter is
    the first implementation; a future custom foundation model gets a new
    class implementing this same interface, and nothing upstream of the
    Render Configuration Compiler changes.
    """

    @abstractmethod
    def capabilities(self) -> CapabilityManifest: ...

    @abstractmethod
    def build_job_payload(self, spec: RenderSpec) -> EngineJobPayload:
        """Translate an engine-agnostic RenderSpec into this engine's
        native container image + input payload."""
        ...

    @abstractmethod
    def parse_result(self, spec: RenderSpec, output: EngineJobOutput) -> RawClip:
        """Translate this engine's raw output back into a normalized
        RawClip for the Post-Processing stage."""
        ...
