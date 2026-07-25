"""Structural validation of the Temporal workflow/activities: confirms
the temporalio SDK accepts the decorators and definitions (update/query/
activity names register correctly). This is the *cheap* check that runs
on every test invocation without needing a live server; real end-to-end
execution against a live Temporal dev server is covered separately in
tests/test_temporal_orchestrator.py (skipped when no server is
reachable) - see docs/adr/0015-temporal-activation.md for how that
became possible in this environment as of Phase 8 WP6 (a real `temporal`
CLI binary, not the SDK's own blocked ephemeral-test-server download).
"""

from __future__ import annotations

from unittest import mock

from render_orchestrator.workflows import ProjectActivities, ProjectGenerationWorkflow
from temporalio import workflow

_ACTIVITY_NAMES = [
    "create_project",
    "generate_creative_plan",
    "approve_storyboard",
    "reject_storyboard",
    "approve_render_plan",
    "reject_render_plan",
    "generate_video",
    "retry_generation",
    "finalize_project",
]


def test_workflow_registers_with_expected_updates_and_queries():
    defn = workflow._Definition.from_class(ProjectGenerationWorkflow)
    assert defn.name == "ProjectGenerationWorkflow"
    assert set(defn.updates.keys()) == {
        "create_project",
        "generate_creative_plan",
        "approve_storyboard",
        "reject_storyboard",
        "approve_render_plan",
        "reject_render_plan",
        "generate_video",
        "retry_generation",
        "finalize_project",
    }
    assert set(defn.queries.keys()) == {"status", "project_id"}


def test_activities_are_registered_with_matching_names():
    for name in _ACTIVITY_NAMES:
        fn = getattr(ProjectActivities, name)
        assert fn.__temporal_activity_definition.name == name


def test_activities_instance_wraps_a_lifecycle_and_lists_all_activities():
    lifecycle = mock.Mock()
    activities = ProjectActivities(lifecycle)
    bound = activities.all_activities()
    assert len(bound) == len(_ACTIVITY_NAMES)
    assert all(callable(fn) for fn in bound)


def test_workflow_instantiates_with_created_initial_status():
    wf = ProjectGenerationWorkflow()
    assert wf.status() == "created"
    assert wf.project_id() is None
