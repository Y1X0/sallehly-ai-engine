from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from video_engine_sdk import RawClip, RenderSpec

from ..errors import ModelUnavailableError
from .interfaces import IEvaluationMetric, MetricResult


def _local_path(uri: str) -> str | None:
    parsed = urlparse(uri)
    if parsed.scheme in ("", "file"):
        return parsed.path if parsed.scheme == "file" else uri
    return None


class DurationConformanceMetric(IEvaluationMetric):
    """Real, CPU-only: does the produced clip's duration match what was
    requested, within `tolerance_sec`? Always available - `RawClip`
    always carries `duration_sec`."""

    name = "duration_conformance"

    def __init__(self, tolerance_sec: float = 0.5) -> None:
        self._tolerance_sec = tolerance_sec

    def compute(self, spec: RenderSpec, clip: RawClip) -> MetricResult:
        diff = abs(clip.duration_sec - spec.duration_sec)
        return MetricResult(self.name, round(diff, 3), passed=diff <= self._tolerance_sec)


class ResolutionConformanceMetric(IEvaluationMetric):
    """Real, CPU-only: does the produced clip's resolution string
    exactly match the requested one?"""

    name = "resolution_conformance"

    def compute(self, spec: RenderSpec, clip: RawClip) -> MetricResult:
        matches = clip.resolution == spec.resolution
        return MetricResult(self.name, 1.0 if matches else 0.0, passed=matches)


class OutputExistsMetric(IEvaluationMetric):
    """Real, CPU-only sanity check: does `clip.storage_uri` resolve to a
    real, non-empty local file? Catches the class of failure where a
    compute provider reports success but produced nothing (or an empty
    stub) - the same failure mode `LocalProvider`'s own stub output
    would trip if misconfigured. Only meaningful for `file://`/bare-path
    URIs - for anything else (e.g. `s3://`) this reports `passed=None`
    rather than guessing, since verifying that would need real network
    access this metric doesn't have."""

    name = "output_exists"

    def compute(self, spec: RenderSpec, clip: RawClip) -> MetricResult:
        path = _local_path(clip.storage_uri)
        if path is None:
            return MetricResult(self.name, 0.0, passed=None)
        exists_nonzero = Path(path).is_file() and Path(path).stat().st_size > 0
        return MetricResult(self.name, 1.0 if exists_nonzero else 0.0, passed=exists_nonzero)


class FVDMetric(IEvaluationMetric):
    """The real Stage 7 integration point for Frechet Video Distance -
    needs a pretrained video feature extractor (typically an I3D
    network) to compare distributions of real vs. generated clips.
    Raises `ModelUnavailableError` unconditionally: no such model is
    installed in this environment. The three metrics above remain
    available without one."""

    name = "fvd"

    def compute(self, spec: RenderSpec, clip: RawClip) -> MetricResult:
        raise ModelUnavailableError(
            "FVDMetric needs a real pretrained video feature extractor (e.g. an I3D network) "
            "to compute Frechet Video Distance - none is installed in this environment. Use "
            "DurationConformanceMetric/ResolutionConformanceMetric/OutputExistsMetric until a "
            "real one is wired in (Phase 9 roadmap Stage 7)."
        )


class CLIPScoreMetric(IEvaluationMetric):
    """The real Stage 7 integration point for text-video alignment
    scoring via CLIP. Raises `ModelUnavailableError` unconditionally -
    the same CLIP dependency
    `cinematic_intelligence.model_adapters.embedding_providers.ClipEmbeddingProvider`
    already needs and doesn't have installed here, reused conceptually
    rather than imported directly to keep `services/training` decoupled
    from `services/cinematic-intelligence`."""

    name = "clip_score"

    def compute(self, spec: RenderSpec, clip: RawClip) -> MetricResult:
        raise ModelUnavailableError(
            "CLIPScoreMetric needs a real CLIP model to score prompt/video alignment - none is "
            "installed in this environment. See "
            "cinematic_intelligence.model_adapters.embedding_providers.ClipEmbeddingProvider for "
            "the same real-but-uninstalled dependency."
        )
