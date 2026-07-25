"""Phase 9 Preparation: the evaluation framework - metric interfaces,
benchmark runner, human evaluation store, quality reports, and
regression detection. `BenchmarkRunner` is exercised against this
project's own real `Wan21Adapter`/`LocalProvider` (fully offline, no
GPU) and against the untrained `SallehlyModelAdapter` (proving the
harness degrades gracefully instead of crashing). See
docs/adr/0021-phase9-preparation.md.
"""

from __future__ import annotations

import pytest
from training import (
    BenchmarkCase,
    BenchmarkResult,
    BenchmarkRunner,
    CLIPScoreMetric,
    DurationConformanceMetric,
    FVDMetric,
    HumanEvalRecord,
    InMemoryHumanEvalStore,
    ModelUnavailableError,
    OutputExistsMetric,
    QualityReport,
    RegressionDetector,
    ResolutionConformanceMetric,
    build_quality_report,
    mean_rating,
)
from training.evaluation.benchmark import BenchmarkCaseResult
from training.evaluation.interfaces import MetricResult
from video_engine_adapter.adapters import SallehlyModelAdapter, Wan21Adapter
from video_engine_adapter.compute import LocalProvider
from video_engine_sdk import RawClip, RenderSpec

_SPEC = RenderSpec(
    schema_version="1.0",
    shot_id="shot_1",
    duration_sec=4.0,
    fps=24,
    resolution="1280x720",
    positive_prompt="a cinematic product shot",
    mode="text_to_video",
)


# --- classical metrics --------------------------------------------------


def test_duration_conformance_metric_passes_within_tolerance():
    clip = RawClip(shot_id="shot_1", storage_uri="file:///dev/null", duration_sec=4.2, resolution="1280x720")
    result = DurationConformanceMetric(tolerance_sec=0.5).compute(_SPEC, clip)
    assert result.passed is True
    assert result.value == pytest.approx(0.2)


def test_duration_conformance_metric_fails_outside_tolerance():
    clip = RawClip(shot_id="shot_1", storage_uri="file:///dev/null", duration_sec=10.0, resolution="1280x720")
    result = DurationConformanceMetric(tolerance_sec=0.5).compute(_SPEC, clip)
    assert result.passed is False


def test_resolution_conformance_metric():
    matching = RawClip(shot_id="shot_1", storage_uri="file:///dev/null", duration_sec=4.0, resolution="1280x720")
    mismatched = RawClip(shot_id="shot_1", storage_uri="file:///dev/null", duration_sec=4.0, resolution="832x480")
    assert ResolutionConformanceMetric().compute(_SPEC, matching).passed is True
    assert ResolutionConformanceMetric().compute(_SPEC, mismatched).passed is False


def test_output_exists_metric_on_a_real_nonempty_file(tmp_path):
    path = tmp_path / "output.bin"
    path.write_bytes(b"not empty")
    clip = RawClip(shot_id="shot_1", storage_uri=f"file://{path}", duration_sec=4.0, resolution="1280x720")
    assert OutputExistsMetric().compute(_SPEC, clip).passed is True


def test_output_exists_metric_on_a_missing_file(tmp_path):
    clip = RawClip(
        shot_id="shot_1", storage_uri=f"file://{tmp_path / 'missing.bin'}", duration_sec=4.0, resolution="1280x720"
    )
    assert OutputExistsMetric().compute(_SPEC, clip).passed is False


def test_output_exists_metric_reports_none_for_non_local_uris():
    clip = RawClip(shot_id="shot_1", storage_uri="s3://bucket/key", duration_sec=4.0, resolution="1280x720")
    assert OutputExistsMetric().compute(_SPEC, clip).passed is None


def test_fvd_and_clip_score_metrics_raise_model_unavailable_error():
    clip = RawClip(shot_id="shot_1", storage_uri="file:///dev/null", duration_sec=4.0, resolution="1280x720")
    with pytest.raises(ModelUnavailableError):
        FVDMetric().compute(_SPEC, clip)
    with pytest.raises(ModelUnavailableError):
        CLIPScoreMetric().compute(_SPEC, clip)


# --- BenchmarkRunner (real GenerationPipeline-equivalent execution) ------


def test_benchmark_runner_succeeds_against_wan21_and_local_provider(tmp_path):
    runner = BenchmarkRunner([DurationConformanceMetric(), ResolutionConformanceMetric(), OutputExistsMetric()])
    case = BenchmarkCase(case_id="case_1", render_spec=_SPEC)

    result = runner.run("wan21-baseline", Wan21Adapter(), LocalProvider(str(tmp_path)), [case])

    assert len(result.case_results) == 1
    case_result = result.case_results[0]
    assert case_result.error is None
    metric_names = {m.name for m in case_result.metric_results}
    assert metric_names == {"duration_conformance", "resolution_conformance", "output_exists"}
    assert all(m.passed for m in case_result.metric_results)


def test_benchmark_runner_records_a_per_case_error_for_an_untrained_engine(tmp_path):
    """Running the benchmark harness against sallehly-v1 before any
    training has happened must degrade gracefully (a recorded per-case
    error), not crash the whole benchmark run - this is exactly the
    scenario Phase 9 will hit the moment a real checkpoint exists to
    benchmark."""
    runner = BenchmarkRunner([DurationConformanceMetric()])
    case = BenchmarkCase(case_id="case_1", render_spec=_SPEC)

    result = runner.run("sallehly-v1-untrained", SallehlyModelAdapter(), LocalProvider(str(tmp_path)), [case])

    assert len(result.case_results) == 1
    case_result = result.case_results[0]
    assert case_result.error is not None
    assert "not" in case_result.error.lower() or "trained" in case_result.error.lower()
    assert case_result.metric_results == ()


# --- Human evaluation -----------------------------------------------------


def test_human_eval_record_validates_rating_range():
    HumanEvalRecord(record_id="r1", version_id="v1", case_id="c1", reviewer_id="rev1", rating=3).validate()
    with pytest.raises(ValueError):
        HumanEvalRecord(record_id="r1", version_id="v1", case_id="c1", reviewer_id="rev1", rating=0).validate()
    with pytest.raises(ValueError):
        HumanEvalRecord(record_id="r1", version_id="v1", case_id="c1", reviewer_id="rev1", rating=6).validate()


def test_in_memory_human_eval_store_save_and_list():
    store = InMemoryHumanEvalStore()
    store.save(HumanEvalRecord(record_id="r1", version_id="v1", case_id="c1", reviewer_id="rev1", rating=4))
    store.save(HumanEvalRecord(record_id="r2", version_id="v1", case_id="c2", reviewer_id="rev2", rating=5))
    store.save(HumanEvalRecord(record_id="r3", version_id="v2", case_id="c1", reviewer_id="rev1", rating=2))

    v1_records = store.list_for_version("v1")
    assert len(v1_records) == 2
    assert mean_rating(v1_records) == 4.5


def test_mean_rating_of_empty_list_is_none():
    assert mean_rating([]) is None


# --- QualityReport --------------------------------------------------------


def _case_result(case_id: str, *, error: str | None = None, values: dict[str, tuple[float, bool | None]] | None = None):
    if error is not None:
        return BenchmarkCaseResult(case_id=case_id, metric_results=(), error=error)
    metrics = tuple(MetricResult(name=name, value=value, passed=passed) for name, (value, passed) in (values or {}).items())
    return BenchmarkCaseResult(case_id=case_id, metric_results=metrics)


def test_build_quality_report_aggregates_metrics_and_errors():
    benchmark_result = BenchmarkResult(
        version_id="v1",
        case_results=(
            _case_result("c1", values={"duration_conformance": (0.1, True), "resolution_conformance": (1.0, True)}),
            _case_result("c2", values={"duration_conformance": (0.9, False), "resolution_conformance": (0.0, False)}),
            _case_result("c3", error="compute job ended with status=failed"),
        ),
    )

    report = build_quality_report(benchmark_result)

    assert report.version_id == "v1"
    assert report.case_count == 3
    assert report.error_count == 1
    assert report.metric_summary["duration_conformance"] == pytest.approx(0.5)
    assert report.pass_rate["duration_conformance"] == pytest.approx(0.5)
    assert report.pass_rate["resolution_conformance"] == pytest.approx(0.5)
    assert report.human_eval_mean_rating is None


def test_build_quality_report_includes_human_eval_mean():
    benchmark_result = BenchmarkResult(version_id="v1", case_results=(_case_result("c1", values={}),))
    human_records = [
        HumanEvalRecord(record_id="r1", version_id="v1", case_id="c1", reviewer_id="rev1", rating=4),
        HumanEvalRecord(record_id="r2", version_id="v1", case_id="c1", reviewer_id="rev2", rating=2),
    ]

    report = build_quality_report(benchmark_result, human_records)
    assert report.human_eval_mean_rating == 3.0


# --- RegressionDetector -----------------------------------------------


def _report(version_id: str, metric_summary: dict[str, float]) -> QualityReport:
    return QualityReport(
        version_id=version_id,
        case_count=1,
        error_count=0,
        metric_summary=metric_summary,
        pass_rate={},
        human_eval_mean_rating=None,
    )


def test_regression_detector_flags_a_drop_in_a_higher_is_better_metric():
    baseline = _report("baseline", {"clip_score": 0.8})
    candidate = _report("candidate", {"clip_score": 0.5})

    detector = RegressionDetector(tolerance=0.05)
    findings = detector.compare(baseline, candidate)

    assert len(findings) == 1
    assert findings[0].regressed is True
    assert detector.has_regression(baseline, candidate) is True


def test_regression_detector_does_not_flag_an_improvement():
    baseline = _report("baseline", {"clip_score": 0.5})
    candidate = _report("candidate", {"clip_score": 0.8})

    detector = RegressionDetector()
    assert detector.has_regression(baseline, candidate) is False


def test_regression_detector_respects_lower_is_better_metrics():
    baseline = _report("baseline", {"fvd": 100.0})
    candidate_worse = _report("worse", {"fvd": 150.0})
    candidate_better = _report("better", {"fvd": 50.0})

    detector = RegressionDetector(higher_is_better={"fvd": False}, tolerance=1.0)

    assert detector.has_regression(baseline, candidate_worse) is True
    assert detector.has_regression(baseline, candidate_better) is False


def test_regression_detector_ignores_metrics_absent_from_the_candidate():
    baseline = _report("baseline", {"clip_score": 0.8, "fvd": 100.0})
    candidate = _report("candidate", {"clip_score": 0.8})

    findings = RegressionDetector().compare(baseline, candidate)
    assert {f.metric_name for f in findings} == {"clip_score"}
