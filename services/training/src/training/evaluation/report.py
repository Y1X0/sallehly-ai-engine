from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .benchmark import BenchmarkResult
from .human_eval import HumanEvalRecord, mean_rating


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class QualityReport:
    """The aggregated verdict on one model version's benchmark run -
    what a promotion decision (`registry.filesystem_registry`'s
    `promote()`, or a human reviewing Stage 8's gate) actually reads,
    rather than re-deriving it from raw per-case metric results every
    time."""

    version_id: str
    case_count: int
    error_count: int
    metric_summary: dict[str, float]
    """metric name -> mean value across every case that produced it."""
    pass_rate: dict[str, float]
    """metric name -> fraction of cases where that metric reported
    `passed=True`, only for metrics that report pass/fail at all."""
    human_eval_mean_rating: float | None
    created_at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version_id": self.version_id,
            "case_count": self.case_count,
            "error_count": self.error_count,
            "metric_summary": self.metric_summary,
            "pass_rate": self.pass_rate,
            "human_eval_mean_rating": self.human_eval_mean_rating,
            "created_at": self.created_at,
        }


def build_quality_report(
    benchmark_result: BenchmarkResult, human_eval_records: list[HumanEvalRecord] | None = None
) -> QualityReport:
    values_by_metric: dict[str, list[float]] = defaultdict(list)
    pass_counts: dict[str, int] = defaultdict(int)
    pass_totals: dict[str, int] = defaultdict(int)
    error_count = 0

    for case_result in benchmark_result.case_results:
        if case_result.error is not None:
            error_count += 1
            continue
        for metric_result in case_result.metric_results:
            values_by_metric[metric_result.name].append(metric_result.value)
            if metric_result.passed is not None:
                pass_totals[metric_result.name] += 1
                if metric_result.passed:
                    pass_counts[metric_result.name] += 1

    metric_summary = {name: round(sum(values) / len(values), 4) for name, values in values_by_metric.items()}
    pass_rate = {name: round(pass_counts[name] / pass_totals[name], 4) for name in pass_totals}

    return QualityReport(
        version_id=benchmark_result.version_id,
        case_count=len(benchmark_result.case_results),
        error_count=error_count,
        metric_summary=metric_summary,
        pass_rate=pass_rate,
        human_eval_mean_rating=mean_rating(human_eval_records or []),
    )
