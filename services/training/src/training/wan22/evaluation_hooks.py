from __future__ import annotations

from video_engine_sdk import IComputeProvider, IVideoEngine

from ..evaluation.benchmark import BenchmarkCase, BenchmarkRunner
from ..evaluation.human_eval import IHumanEvalStore
from ..evaluation.interfaces import IEvaluationMetric
from ..evaluation.regression import RegressionDetector, RegressionFinding
from ..evaluation.report import QualityReport, build_quality_report


class Wan22EvaluationHook:
    """The Stage 7 eval-cadence hook `DryRunTrainer`'s `on_step`
    docstring already anticipated, wired to a real `IBenchmarkRunner`
    now that there's a real trainer to attach it to. Meant to be passed
    as `Wan22LoRATrainer(on_checkpoint=hook)`: after every paired
    checkpoint, runs the existing (real) `BenchmarkRunner` against
    `engine`/`compute_provider`, builds a `QualityReport`, and keeps
    enough history to run `RegressionDetector` against a prior step.

    Requires a real `IVideoEngine` + `IComputeProvider` to be handed in
    by the caller - this hook does not import or construct
    `video_engine_adapter` itself, matching the rest of
    `services/training`'s dependency-light discipline. Until a trained
    Wan2.2 `IVideoEngine` exists, callers point this at the untrained
    `SallehlyModelAdapter` (or `Wan21Adapter`, for a smoke test) - the
    benchmark then correctly records a per-case error rather than
    crashing, exactly like `BenchmarkRunner` already proves in
    `tests/test_training_evaluation.py`.
    """

    def __init__(
        self,
        *,
        engine: IVideoEngine,
        compute_provider: IComputeProvider,
        cases: list[BenchmarkCase],
        metrics: list[IEvaluationMetric],
        human_eval_store: IHumanEvalStore | None = None,
        regression_detector: RegressionDetector | None = None,
    ) -> None:
        self._runner = BenchmarkRunner(metrics)
        self._engine = engine
        self._compute_provider = compute_provider
        self._cases = cases
        self._human_eval_store = human_eval_store
        self._regression_detector = regression_detector or RegressionDetector()
        self._reports_by_step: dict[int, QualityReport] = {}

    def __call__(self, step: int, checkpoint_ids: list[str]) -> QualityReport:
        version_id = f"step-{step:06d}"
        result = self._runner.run(version_id, self._engine, self._compute_provider, self._cases)
        human_records = (
            self._human_eval_store.list_for_version(version_id) if self._human_eval_store is not None else None
        )
        report = build_quality_report(result, human_records)
        self._reports_by_step[step] = report
        return report

    def report_for_step(self, step: int) -> QualityReport | None:
        return self._reports_by_step.get(step)

    def regression_against(self, baseline_step: int, candidate_step: int) -> list[RegressionFinding] | None:
        baseline = self._reports_by_step.get(baseline_step)
        candidate = self._reports_by_step.get(candidate_step)
        if baseline is None or candidate is None:
            return None
        return self._regression_detector.compare(baseline, candidate)
