"""ProjectLifecycle: the core business logic behind both
SyncProjectOrchestrator and the Temporal workflow's activities. Tests
here exercise every transition directly, including invalid transitions,
reject/regenerate on both gates, and the generation-failure path.
"""

from __future__ import annotations

import pytest
from conftest import SAMPLE_BRIEF, build_stack
from persistence import ProjectStatus
from render_orchestrator import ProjectLifecycleError
from video_engine_sdk import ComputeJobHandle, ComputeJobStatus, EngineJobOutput, EngineJobPayload, IComputeProvider


def test_create_project_starts_at_created():
    stack = build_stack()
    record = stack.lifecycle.create_project(**SAMPLE_BRIEF)
    assert record.status == ProjectStatus.CREATED
    assert stack.project_store.get(record.project_id) is record


def test_generate_creative_plan_reaches_waiting_storyboard_approval():
    stack = build_stack()
    record = stack.lifecycle.create_project(**SAMPLE_BRIEF)

    record = stack.lifecycle.generate_creative_plan(record.project_id)

    assert record.status == ProjectStatus.WAITING_STORYBOARD_APPROVAL
    assert stack.memory.latest(record.project_id, "director_plan") is not None
    assert stack.memory.latest(record.project_id, "storyboard") is not None


def test_full_gate_sequence_reaches_completed():
    stack = build_stack()
    record = stack.lifecycle.create_project(**SAMPLE_BRIEF)
    stack.lifecycle.generate_creative_plan(record.project_id)

    record = stack.lifecycle.approve_storyboard(record.project_id)
    assert record.status == ProjectStatus.WAITING_RENDER_APPROVAL

    record = stack.lifecycle.approve_render_plan(record.project_id)
    assert record.status == ProjectStatus.APPROVED

    record = stack.lifecycle.generate_video(record.project_id)
    assert record.status == ProjectStatus.COMPLETED
    assert len(record.generation_job_ids) > 0
    assert len(record.asset_ids) == len(record.generation_job_ids)


def test_wrong_state_transition_raises():
    stack = build_stack()
    record = stack.lifecycle.create_project(**SAMPLE_BRIEF)

    with pytest.raises(ProjectLifecycleError, match="created, expected waiting_storyboard_approval"):
        stack.lifecycle.approve_storyboard(record.project_id)


def test_unknown_project_raises():
    stack = build_stack()
    with pytest.raises(ProjectLifecycleError, match="No such project"):
        stack.lifecycle.generate_creative_plan("does-not-exist")


def test_reject_storyboard_regenerates_and_returns_to_waiting_approval():
    stack = build_stack()
    record = stack.lifecycle.create_project(**SAMPLE_BRIEF)
    stack.lifecycle.generate_creative_plan(record.project_id)

    first_storyboard = stack.memory.latest(record.project_id, "storyboard").content

    record = stack.lifecycle.reject_storyboard(record.project_id, ["too static, add movement"])

    assert record.status == ProjectStatus.WAITING_STORYBOARD_APPROVAL
    assert record.rejected_stage is None  # cleared once regeneration succeeds
    second_storyboard = stack.memory.latest(record.project_id, "storyboard").content
    assert second_storyboard["director_plan_version"] != first_storyboard["director_plan_version"]

    feedback_history = stack.memory.history(record.project_id, "story_outline")
    assert len(feedback_history) == 2  # original + regenerated


def test_reject_render_plan_recompiles_with_new_quality_tier():
    stack = build_stack()
    record = stack.lifecycle.create_project(**SAMPLE_BRIEF)
    stack.lifecycle.generate_creative_plan(record.project_id)
    stack.lifecycle.approve_storyboard(record.project_id)

    first_plan = stack.memory.latest(record.project_id, "render_plan").content
    assert first_plan["render_specs"][0]["quality_tier"] == "final"

    record = stack.lifecycle.reject_render_plan(
        record.project_id, ["render looked rough"], quality_tier="preview"
    )

    assert record.status == ProjectStatus.WAITING_RENDER_APPROVAL
    second_plan = stack.memory.latest(record.project_id, "render_plan").content
    assert second_plan["render_specs"][0]["quality_tier"] == "preview"


def test_events_published_in_order_through_full_flow():
    stack = build_stack()
    record = stack.lifecycle.create_project(**SAMPLE_BRIEF)
    stack.lifecycle.generate_creative_plan(record.project_id)
    stack.lifecycle.approve_storyboard(record.project_id)
    stack.lifecycle.approve_render_plan(record.project_id)
    stack.lifecycle.generate_video(record.project_id)

    event_types = [e.type.value for e in stack.events.history]
    assert event_types == [
        "project_created",
        "plan_generated",
        "storyboard_ready",
        "render_ready",
        "generation_started",
        "generation_completed",
    ]


class _AlwaysFailingComputeProvider(IComputeProvider):
    provider_id = "always-failing"

    def submit(self, payload: EngineJobPayload) -> ComputeJobHandle:
        return ComputeJobHandle(provider_id=self.provider_id, external_job_id="doomed")

    def get_status(self, handle: ComputeJobHandle) -> ComputeJobStatus:
        return ComputeJobStatus.FAILED

    def fetch_output(self, handle: ComputeJobHandle) -> EngineJobOutput:
        raise AssertionError("should not be called")

    def cancel(self, handle: ComputeJobHandle) -> None:
        pass


def test_generate_video_failure_path_sets_status_failed_and_publishes_event():
    stack = build_stack(compute_provider=_AlwaysFailingComputeProvider())
    record = stack.lifecycle.create_project(**SAMPLE_BRIEF)
    stack.lifecycle.generate_creative_plan(record.project_id)
    stack.lifecycle.approve_storyboard(record.project_id)
    stack.lifecycle.approve_render_plan(record.project_id)

    record = stack.lifecycle.generate_video(record.project_id)

    assert record.status == ProjectStatus.FAILED
    assert record.error_message is not None
    assert record.asset_ids == []
    assert stack.events.history[-1].type.value == "generation_failed"


class _SwitchableComputeProvider(IComputeProvider):
    """Fails every job while `.fail` is True, succeeds identically to
    LocalProvider once flipped - simulates a transient outage that
    retry-generation recovers from without needing a new render plan."""

    provider_id = "switchable"

    def __init__(self) -> None:
        self.fail = True
        self._handles: dict[str, bool] = {}

    def submit(self, payload: EngineJobPayload) -> ComputeJobHandle:
        job_id = f"job-{len(self._handles)}"
        self._handles[job_id] = self.fail
        return ComputeJobHandle(provider_id=self.provider_id, external_job_id=job_id)

    def get_status(self, handle: ComputeJobHandle) -> ComputeJobStatus:
        failed = self._handles[handle.external_job_id]
        return ComputeJobStatus.FAILED if failed else ComputeJobStatus.SUCCEEDED

    def fetch_output(self, handle: ComputeJobHandle) -> EngineJobOutput:
        return EngineJobOutput(output_uri=f"file:///tmp/{handle.external_job_id}.mp4", engine_metadata={})

    def cancel(self, handle: ComputeJobHandle) -> None:
        pass


def test_retry_generation_requires_failed_status():
    stack = build_stack()
    record = stack.lifecycle.create_project(**SAMPLE_BRIEF)

    with pytest.raises(ProjectLifecycleError, match="created, expected failed"):
        stack.lifecycle.retry_generation(record.project_id)


def test_retry_generation_recovers_after_transient_failure():
    compute = _SwitchableComputeProvider()
    stack = build_stack(compute_provider=compute)
    record = stack.lifecycle.create_project(**SAMPLE_BRIEF)
    stack.lifecycle.generate_creative_plan(record.project_id)
    stack.lifecycle.approve_storyboard(record.project_id)
    stack.lifecycle.approve_render_plan(record.project_id)

    record = stack.lifecycle.generate_video(record.project_id)
    assert record.status == ProjectStatus.FAILED
    assert record.error_message is not None

    compute.fail = False
    record = stack.lifecycle.retry_generation(record.project_id)

    assert record.status == ProjectStatus.COMPLETED
    assert record.error_message is None
    assert len(record.asset_ids) > 0
    assert stack.events.history[-1].type.value == "generation_completed"
