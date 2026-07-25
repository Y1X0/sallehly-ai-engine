from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .report import QualityReport


@dataclass(frozen=True)
class RegressionFinding:
    metric_name: str
    baseline_value: float
    candidate_value: float
    delta: float
    regressed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric_name": self.metric_name,
            "baseline_value": self.baseline_value,
            "candidate_value": self.candidate_value,
            "delta": self.delta,
            "regressed": self.regressed,
        }


class RegressionDetector:
    """Compares a candidate `QualityReport` against a baseline one
    (typically the currently-PRODUCTION model version's own last report)
    - the automated half of the Stage 8 benchmarking gate
    (docs/adr/0021-phase9-preparation.md): a candidate must not regress
    on any metric by more than `tolerance` before it's worth a human
    even looking at it.

    `higher_is_better` defaults every metric to "higher is better" (true
    for pass-rate-shaped and score-shaped metrics) - pass an explicit
    `False` entry for any metric where lower is better (e.g. a distance
    metric like FVD, once real) so a drop in that number is correctly
    read as an improvement, not a regression.
    """

    def __init__(self, *, higher_is_better: dict[str, bool] | None = None, tolerance: float = 0.0) -> None:
        self._higher_is_better = higher_is_better or {}
        self._tolerance = tolerance

    def compare(self, baseline: QualityReport, candidate: QualityReport) -> list[RegressionFinding]:
        findings: list[RegressionFinding] = []
        for metric_name, baseline_value in baseline.metric_summary.items():
            if metric_name not in candidate.metric_summary:
                continue
            candidate_value = candidate.metric_summary[metric_name]
            delta = round(candidate_value - baseline_value, 4)
            higher_is_better = self._higher_is_better.get(metric_name, True)
            regressed = (delta < -self._tolerance) if higher_is_better else (delta > self._tolerance)
            findings.append(
                RegressionFinding(
                    metric_name=metric_name,
                    baseline_value=baseline_value,
                    candidate_value=candidate_value,
                    delta=delta,
                    regressed=regressed,
                )
            )
        return findings

    def has_regression(self, baseline: QualityReport, candidate: QualityReport) -> bool:
        return any(finding.regressed for finding in self.compare(baseline, candidate))
