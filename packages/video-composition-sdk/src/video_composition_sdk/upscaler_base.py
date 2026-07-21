from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class IUpscaler(ABC):
    """Interface for a future real quality-enhancement step (e.g.
    Real-ESRGAN-style video upscaling, RIFE-style frame interpolation) -
    prepared per Phase 6's scope ("prepare interfaces for: video
    upscaling, frame interpolation, quality enhancement"), not
    implemented. Real upscaling needs a GPU model deployment, the same
    class of limitation as Wan2.1 inference (ADR 0010) - honest about
    that rather than faking it. `PassthroughUpscaler`
    (services/post-processing) is the only concrete implementation
    today: it copies input to output unchanged, letting the rest of the
    pipeline (Export Service, Asset Packaging) be built and tested
    against this interface now."""

    @abstractmethod
    def upscale(self, input_path: str | Path, output_path: str | Path, target_resolution: str) -> str:
        """Returns the output path/URI."""
        ...

    @abstractmethod
    def interpolate_frames(self, input_path: str | Path, output_path: str | Path, target_fps: int) -> str:
        """Returns the output path/URI."""
        ...
