from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from video_engine_sdk import ComputeJobStatus, IComputeProvider, IVideoEngine, RenderSpec

from .interfaces import IEvaluationMetric, MetricResult


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class BenchmarkCase:
    """One golden, fixed `RenderSpec` in a benchmark set - the "same
    prompt through every candidate" fixture the Phase 9 roadmap's Stage
    8 benchmarking gate needs. Kept separate from
    `render_orchestrator.GenerationPipeline`'s job-tracking machinery on
    purpose: a benchmark run is a comparison exercise across many
    engine/checkpoint candidates, not a real generation job that needs
    persistence, retries, or an `AssetManager` entry."""

    case_id: str
    render_spec: RenderSpec


@dataclass(frozen=True)
class BenchmarkCaseResult:
    case_id: str
    metric_results: tuple[MetricResult, ...]
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "metric_results": [m.to_dict() for m in self.metric_results],
            "error": self.error,
        }


@dataclass(frozen=True)
class BenchmarkResult:
    version_id: str
    case_results: tuple[BenchmarkCaseResult, ...]
    created_at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version_id": self.version_id,
            "case_results": [c.to_dict() for c in self.case_results],
            "created_at": self.created_at,
        }


class IBenchmarkRunner(ABC):
    @abstractmethod
    def run(
        self,
        version_id: str,
        engine: IVideoEngine,
        compute_provider: IComputeProvider,
        cases: list[BenchmarkCase],
    ) -> BenchmarkResult: ...


class BenchmarkRunner(IBenchmarkRunner):
    """Real orchestration against the actual `IVideoEngine`/
    `IComputeProvider` contract (`packages/video-engine-sdk`) - the same
    four-call dance `GenerationPipeline._run_once` performs
    (`build_job_payload` -> `submit`/poll/`fetch_output` -> `parse_result`),
    reimplemented directly here rather than depending on
    `services/render-orchestrator` (which would pull in persistence,
    cache, and cinematic-intelligence transitively just to run a
    benchmark). Genuinely executable today with no GPU at all using
    `Wan21Adapter` + `LocalProvider` (the same fully-offline pair this
    codebase's own test suite already exercises); pointing `engine` at
    an untrained `SallehlyModelAdapter` correctly surfaces
    `SallehlyModelNotTrainedError` as a per-case `error`, not a crash -
    proving this harness is genuinely ready to benchmark a real
    checkpoint the moment Phase 9 produces one.
    """

    def __init__(
        self, metrics: list[IEvaluationMetric], *, poll_interval_sec: float = 0.0, poll_timeout_sec: float = 60.0
    ) -> None:
        self._metrics = metrics
        self._poll_interval_sec = poll_interval_sec
        self._poll_timeout_sec = poll_timeout_sec

    def run(
        self,
        version_id: str,
        engine: IVideoEngine,
        compute_provider: IComputeProvider,
        cases: list[BenchmarkCase],
    ) -> BenchmarkResult:
        case_results = [self._run_case(case, engine, compute_provider) for case in cases]
        return BenchmarkResult(version_id=version_id, case_results=tuple(case_results))

    def _run_case(self, case: BenchmarkCase, engine: IVideoEngine, compute_provider: IComputeProvider) -> BenchmarkCaseResult:
        try:
            payload = engine.build_job_payload(case.render_spec)
            handle = compute_provider.submit(payload)
            status = self._await_completion(compute_provider, handle)
            if status != ComputeJobStatus.SUCCEEDED:
                return BenchmarkCaseResult(
                    case_id=case.case_id, metric_results=(), error=f"compute job ended with status={status.value}"
                )
            output = compute_provider.fetch_output(handle)
            clip = engine.parse_result(case.render_spec, output)
            results = tuple(metric.compute(case.render_spec, clip) for metric in self._metrics)
            return BenchmarkCaseResult(case_id=case.case_id, metric_results=results)
        except Exception as exc:  # noqa: BLE001 - any failure means this case failed, recorded not raised
            return BenchmarkCaseResult(case_id=case.case_id, metric_results=(), error=str(exc))

    def _await_completion(self, compute_provider: IComputeProvider, handle: Any) -> ComputeJobStatus:
        deadline = time.monotonic() + self._poll_timeout_sec
        while True:
            status = compute_provider.get_status(handle)
            if status in (ComputeJobStatus.SUCCEEDED, ComputeJobStatus.FAILED, ComputeJobStatus.CANCELLED):
                return status
            if time.monotonic() > deadline:
                raise TimeoutError("Benchmark case polling timed out")
            if self._poll_interval_sec:
                time.sleep(self._poll_interval_sec)
