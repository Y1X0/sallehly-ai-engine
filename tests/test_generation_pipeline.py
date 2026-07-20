"""Tests for GenerationPipeline: RenderSpec dict -> Wan21Adapter ->
IComputeProvider -> GenerationJob -> AssetManager. Uses LocalProvider (no
GPU) for the happy path, and small test doubles for the failure/retry
paths - never touches a real network or GPU.
"""

from __future__ import annotations

from asset_manager import AssetManager
from render_orchestrator import GenerationJobStatus, GenerationPipeline, InMemoryGenerationJobStore
from video_engine_adapter.adapters import Wan21Adapter
from video_engine_adapter.compute import LocalProvider
from video_engine_sdk import ComputeJobHandle, ComputeJobStatus, EngineJobOutput, EngineJobPayload, IComputeProvider

SAMPLE_RENDER_SPEC = {
    "schema_version": "1.0",
    "shot_id": "shot_0_0",
    "duration_sec": 3.0,
    "fps": 24,
    "resolution": "832x480",
    "aspect_ratio": "16:9",
    "mode": "text_to_video",
    "positive_prompt": "a minimalist watch on marble, golden hour lighting",
    "negative_prompt": "blurry, watermark",
    "seed": 42,
    "motion_strength": 45.0,
    "camera": {
        "shot_type": "medium",
        "focal_length_mm_equiv": 35,
        "angle": "eye_level",
        "movement": {"type": "static", "speed": "slow", "easing": "ease_in_out"},
        "depth_of_field": "medium",
    },
    "lighting": {
        "time_of_day": "golden_hour",
        "mood": "warm and intimate",
        "key_light": {"direction": "side", "hardness": "soft", "color_temp_kelvin": 3200},
        "fill_light_ratio": 0.5,
        "rim_light": False,
        "volumetric_effects": {"enabled": True, "intensity": "subtle"},
        "grading_direction": "warm highlights, soft shadows",
    },
    "engine_id": "wan2.1",
    "quality_tier": "final",
}


class AlwaysFailingComputeProvider(IComputeProvider):
    """Test double: every submit succeeds, but the job always ends up FAILED."""

    provider_id = "always-failing"

    def submit(self, payload: EngineJobPayload) -> ComputeJobHandle:
        return ComputeJobHandle(provider_id=self.provider_id, external_job_id="doomed-job")

    def get_status(self, handle: ComputeJobHandle) -> ComputeJobStatus:
        return ComputeJobStatus.FAILED

    def fetch_output(self, handle: ComputeJobHandle) -> EngineJobOutput:
        raise AssertionError("fetch_output should never be called for a failed job")

    def cancel(self, handle: ComputeJobHandle) -> None:
        pass


class FlakyThenSucceedsComputeProvider(IComputeProvider):
    """Test double: submit() raises for the first `fail_times` calls, then
    delegates to a real LocalProvider - used to exercise
    GenerationPipeline's job-level retry."""

    provider_id = "flaky"

    def __init__(self, fail_times: int) -> None:
        self._fail_times = fail_times
        self._attempts = 0
        self._delegate = LocalProvider()

    def submit(self, payload: EngineJobPayload) -> ComputeJobHandle:
        self._attempts += 1
        if self._attempts <= self._fail_times:
            raise RuntimeError(f"simulated transient failure (attempt {self._attempts})")
        return self._delegate.submit(payload)

    def get_status(self, handle: ComputeJobHandle) -> ComputeJobStatus:
        return self._delegate.get_status(handle)

    def fetch_output(self, handle: ComputeJobHandle) -> EngineJobOutput:
        return self._delegate.fetch_output(handle)

    def cancel(self, handle: ComputeJobHandle) -> None:
        self._delegate.cancel(handle)


def test_generate_shot_succeeds_with_local_provider(tmp_path):
    pipeline = GenerationPipeline(
        engine=Wan21Adapter(),
        compute_provider=LocalProvider(output_dir=str(tmp_path)),
        asset_manager=AssetManager(),
    )

    job = pipeline.generate_shot("proj_1", SAMPLE_RENDER_SPEC)

    assert job.status == GenerationJobStatus.COMPLETED
    assert job.engine_id == "wan2.1"
    assert job.compute_provider_id == "local"
    assert job.external_job_id is not None
    assert job.output_asset_id is not None
    assert job.error_message is None
    job.validate()


def test_generate_shot_registers_asset_with_asset_manager(tmp_path):
    assets = AssetManager()
    pipeline = GenerationPipeline(
        engine=Wan21Adapter(),
        compute_provider=LocalProvider(output_dir=str(tmp_path)),
        asset_manager=assets,
    )

    job = pipeline.generate_shot("proj_1", SAMPLE_RENDER_SPEC)

    record = assets.get(job.output_asset_id)
    assert record is not None
    assert record["kind"] == "video"
    assert record["project_id"] == "proj_1"
    assert len(record["versions"]) == 1


def test_generate_plan_runs_every_render_spec(tmp_path):
    pipeline = GenerationPipeline(
        engine=Wan21Adapter(),
        compute_provider=LocalProvider(output_dir=str(tmp_path)),
    )
    render_plan = {
        "project_id": "proj_1",
        "render_specs": [
            SAMPLE_RENDER_SPEC,
            {**SAMPLE_RENDER_SPEC, "shot_id": "shot_0_1"},
        ],
    }

    jobs = pipeline.generate_plan(render_plan)

    assert len(jobs) == 2
    assert all(job.status == GenerationJobStatus.COMPLETED for job in jobs)
    assert {job.shot_id for job in jobs} == {"shot_0_0", "shot_0_1"}


def test_generate_shot_marks_job_failed_after_exhausting_retries():
    job_store = InMemoryGenerationJobStore()
    pipeline = GenerationPipeline(
        engine=Wan21Adapter(),
        compute_provider=AlwaysFailingComputeProvider(),
        job_store=job_store,
        max_retries=2,
        poll_interval_sec=0.0,
    )

    job = pipeline.generate_shot("proj_2", SAMPLE_RENDER_SPEC)

    assert job.status == GenerationJobStatus.FAILED
    assert job.retry_count == 2
    assert "status=failed" in job.error_message
    assert job.output_asset_id is None
    assert job_store.get(job.job_id) is job


def test_generate_shot_retries_and_recovers_from_transient_failures():
    pipeline = GenerationPipeline(
        engine=Wan21Adapter(),
        compute_provider=FlakyThenSucceedsComputeProvider(fail_times=2),
        max_retries=2,
    )

    job = pipeline.generate_shot("proj_3", SAMPLE_RENDER_SPEC)

    assert job.status == GenerationJobStatus.COMPLETED
    assert job.retry_count == 2  # failed twice (attempts 0, 1) before succeeding on attempt 2


def test_generate_shot_gives_up_if_retries_insufficient():
    pipeline = GenerationPipeline(
        engine=Wan21Adapter(),
        compute_provider=FlakyThenSucceedsComputeProvider(fail_times=5),
        max_retries=1,
    )

    job = pipeline.generate_shot("proj_4", SAMPLE_RENDER_SPEC)

    assert job.status == GenerationJobStatus.FAILED
    assert "simulated transient failure" in job.error_message
