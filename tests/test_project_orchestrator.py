from __future__ import annotations

from conftest import SAMPLE_BRIEF, build_stack
from persistence import ProjectStatus


def test_run_to_completion_drives_full_flow_with_auto_approval():
    stack = build_stack()
    record = stack.orchestrator.create_project(**SAMPLE_BRIEF)

    record = stack.orchestrator.run_to_completion(record.project_id)

    assert record.status == ProjectStatus.COMPLETED
    assert len(record.asset_ids) > 0


def test_orchestrator_methods_match_lifecycle_step_by_step():
    stack = build_stack()
    record = stack.orchestrator.create_project(**SAMPLE_BRIEF)

    record = stack.orchestrator.generate_creative_plan(record.project_id)
    assert record.status == ProjectStatus.WAITING_STORYBOARD_APPROVAL

    record = stack.orchestrator.reject_storyboard(record.project_id, ["needs more movement"])
    assert record.status == ProjectStatus.WAITING_STORYBOARD_APPROVAL

    record = stack.orchestrator.approve_storyboard(record.project_id)
    assert record.status == ProjectStatus.WAITING_RENDER_APPROVAL

    record = stack.orchestrator.reject_render_plan(record.project_id, ["bump quality"], quality_tier="final")
    assert record.status == ProjectStatus.WAITING_RENDER_APPROVAL

    record = stack.orchestrator.approve_render_plan(record.project_id)
    assert record.status == ProjectStatus.APPROVED

    record = stack.orchestrator.generate_video(record.project_id)
    assert record.status == ProjectStatus.COMPLETED


def test_two_independent_projects_do_not_interfere():
    stack = build_stack()
    first = stack.orchestrator.create_project(**SAMPLE_BRIEF)
    second = stack.orchestrator.create_project(**{**SAMPLE_BRIEF, "prompt": "A calm minimalist tea ad"})

    stack.orchestrator.run_to_completion(first.project_id)

    # second project is untouched by the first's progress
    fetched_second = stack.project_store.get(second.project_id)
    assert fetched_second.status == ProjectStatus.CREATED
