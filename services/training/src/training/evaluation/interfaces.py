from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from video_engine_sdk import RawClip, RenderSpec


@dataclass(frozen=True)
class MetricResult:
    name: str
    value: float
    passed: bool | None
    """`None` when this metric only ever reports a value with no
    pass/fail threshold (e.g. a raw similarity score a human still has
    to interpret), as opposed to `True`/`False` for a metric with a
    real conformance threshold (duration/resolution match)."""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "value": self.value, "passed": self.passed}


class IEvaluationMetric(ABC):
    """One scoring function comparing what was requested (`RenderSpec`)
    against what was produced (`RawClip`). `metrics.py` has real,
    classical implementations (duration/resolution conformance, output
    existence) needing no model, and real integration points for
    model-backed metrics (FVD, CLIP-score) that raise
    `ModelUnavailableError` until a real video/vision model is wired in
    - same honesty pattern as every other model-gated component in this
    codebase."""

    name: str

    @abstractmethod
    def compute(self, spec: RenderSpec, clip: RawClip) -> MetricResult: ...
