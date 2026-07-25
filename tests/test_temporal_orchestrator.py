"""Real, live-executed Temporal integration tests: TemporalProjectOrchestrator
driven through an actual `temporal` CLI dev server plus an actual
in-process worker running the real ProjectGenerationWorkflow/
ProjectActivities - not mocked, not just structurally validated.

Mirrors tests/test_project_orchestrator.py's scenarios (which exercise
SyncProjectOrchestrator) to prove behavioral parity between the two
IProjectOrchestrator implementations, as ADR 0010/0015 always intended.

Skipped entirely if no Temporal server is reachable at
TEMPORAL_ADDRESS - see docs/DEV_SETUP.md for how to run one locally
(`temporal server start-dev`, a real CLI binary - this sandbox's earlier
"not executable" finding, ADR 0010, was specifically about the SDK's own
ephemeral-test-server auto-downloader hitting a blocked host; a
manually-provisioned real server has no such restriction and is also
more representative of a real deployment - see ADR 0015).
"""

from __future__ import annotations

import asyncio
import os
import threading
import uuid

import pytest
from conftest import SAMPLE_BRIEF, build_stack
from persistence import ProjectStatus
from render_orchestrator import ProjectLifecycleError
from render_orchestrator.workflows import TemporalProjectOrchestrator, build_worker
from temporalio.client import Client

TEMPORAL_ADDRESS = os.environ.get("TEMPORAL_ADDRESS", "127.0.0.1:7233")
TEMPORAL_NAMESPACE = os.environ.get("TEMPORAL_NAMESPACE", "default")


def _server_reachable() -> bool:
    async def _check() -> None:
        await Client.connect(TEMPORAL_ADDRESS, namespace=TEMPORAL_NAMESPACE)

    try:
        asyncio.run(_check())
        return True
    except Exception:  # noqa: BLE001 - any connect failure means "skip", not "fail"
        return False


pytestmark = pytest.mark.skipif(
    not _server_reachable(),
    reason=f"No live Temporal server reachable at {TEMPORAL_ADDRESS} - see docs/DEV_SETUP.md",
)


@pytest.fixture(scope="module")
def temporal_stack():
    """One real worker (background thread, its own event loop) backed
    by one real Stack (LocalHeuristicLLMProvider + Wan21Adapter +
    LocalProvider + a real CinematicIntelligenceCoordinator +
    PostProductionRunner - the same fully-offline stack every other
    integration test in this repo uses), shared across every test in
    this module - mirrors one worker process serving many projects in
    production."""
    stack = build_stack(with_cinematic_intelligence=True, with_post_production=True)
    client = asyncio.run(Client.connect(TEMPORAL_ADDRESS, namespace=TEMPORAL_NAMESPACE))
    task_queue = f"test-project-tq-{uuid.uuid4().hex[:8]}"

    ready = threading.Event()
    stop = threading.Event()

    async def _serve() -> None:
        # build_worker() must be called from *inside* a running event
        # loop - temporalio's Worker constructor calls
        # asyncio.get_running_loop() internally while validating the
        # workflow - so this can't be built in the (sync) fixture body
        # above and merely entered here.
        worker = build_worker(client, task_queue, stack.lifecycle)
        async with worker:
            ready.set()
            while not stop.is_set():
                await asyncio.sleep(0.05)

    thread = threading.Thread(target=lambda: asyncio.run(_serve()), daemon=True)
    thread.start()
    assert ready.wait(timeout=15), "worker did not start within 15s"

    orchestrator = TemporalProjectOrchestrator(client, task_queue)
    yield stack, orchestrator

    stop.set()
    thread.join(timeout=15)


def test_orchestrator_methods_match_lifecycle_step_by_step(temporal_stack):
    _, orchestrator = temporal_stack
    record = orchestrator.create_project(**SAMPLE_BRIEF)
    assert record.status == ProjectStatus.CREATED

    record = orchestrator.generate_creative_plan(record.project_id)
    assert record.status == ProjectStatus.WAITING_STORYBOARD_APPROVAL

    record = orchestrator.reject_storyboard(record.project_id, ["needs more movement"])
    assert record.status == ProjectStatus.WAITING_STORYBOARD_APPROVAL

    record = orchestrator.approve_storyboard(record.project_id)
    assert record.status == ProjectStatus.WAITING_RENDER_APPROVAL

    record = orchestrator.reject_render_plan(record.project_id, ["bump quality"], quality_tier="final")
    assert record.status == ProjectStatus.WAITING_RENDER_APPROVAL

    record = orchestrator.approve_render_plan(record.project_id)
    assert record.status == ProjectStatus.APPROVED

    record = orchestrator.generate_video(record.project_id)
    assert record.status == ProjectStatus.COMPLETED
    assert len(record.asset_ids) > 0


def test_wrong_state_transition_raises_project_lifecycle_error_not_a_temporal_wrapper(temporal_stack):
    # The critical compatibility check: apps/api's `_run()` helper does
    # `except ProjectLifecycleError: raise HTTPException(409, ...)` - if
    # this surfaced as WorkflowUpdateFailedError instead, every 409
    # response apps/api relies on would break silently the moment
    # ORCHESTRATOR=temporal is selected.
    _, orchestrator = temporal_stack
    record = orchestrator.create_project(**SAMPLE_BRIEF)

    with pytest.raises(ProjectLifecycleError, match="created, expected waiting_storyboard_approval"):
        orchestrator.approve_storyboard(record.project_id)


def test_retry_generation_requires_failed_status(temporal_stack):
    _, orchestrator = temporal_stack
    record = orchestrator.create_project(**SAMPLE_BRIEF)
    orchestrator.generate_creative_plan(record.project_id)
    orchestrator.approve_storyboard(record.project_id)
    orchestrator.approve_render_plan(record.project_id)
    record = orchestrator.generate_video(record.project_id)
    assert record.status == ProjectStatus.COMPLETED

    with pytest.raises(ProjectLifecycleError, match="completed, expected failed"):
        orchestrator.retry_generation(record.project_id)


def test_two_independent_projects_do_not_interfere(temporal_stack):
    stack, orchestrator = temporal_stack
    first = orchestrator.create_project(**SAMPLE_BRIEF)
    second = orchestrator.create_project(**{**SAMPLE_BRIEF, "prompt": "A calm minimalist tea ad"})

    orchestrator.generate_creative_plan(first.project_id)
    orchestrator.approve_storyboard(first.project_id)
    orchestrator.approve_render_plan(first.project_id)
    orchestrator.generate_video(first.project_id)

    fetched_second = stack.project_store.get(second.project_id)
    assert fetched_second.status == ProjectStatus.CREATED


def test_finalize_project_requires_completed_status(temporal_stack):
    _, orchestrator = temporal_stack
    record = orchestrator.create_project(**SAMPLE_BRIEF)

    with pytest.raises(ProjectLifecycleError, match="created, expected completed"):
        orchestrator.finalize_project(record.project_id)


def test_project_state_survives_a_worker_restart():
    # The actual point of Temporal (ADR 0010's whole justification for
    # this durable path existing at all): stop the worker mid-project,
    # start a brand-new one on the *same* task queue, and prove the
    # remaining steps still complete correctly using only the durable
    # event history - not any in-process state the first worker held.
    # Self-contained (own Stack/worker/task queue) rather than sharing
    # the module fixture, so stopping a worker here can't affect other
    # tests in this file.
    stack = build_stack()
    client = asyncio.run(Client.connect(TEMPORAL_ADDRESS, namespace=TEMPORAL_NAMESPACE))
    task_queue = f"test-restart-tq-{uuid.uuid4().hex[:8]}"
    orchestrator = TemporalProjectOrchestrator(client, task_queue)

    def _serve(lifecycle, stop: threading.Event, ready: threading.Event) -> None:
        async def _run() -> None:
            async with build_worker(client, task_queue, lifecycle):
                ready.set()
                while not stop.is_set():
                    await asyncio.sleep(0.05)

        asyncio.run(_run())

    first_ready, first_stop = threading.Event(), threading.Event()
    first_thread = threading.Thread(target=_serve, args=(stack.lifecycle, first_stop, first_ready), daemon=True)
    first_thread.start()
    assert first_ready.wait(timeout=15)

    record = orchestrator.create_project(**SAMPLE_BRIEF)
    record = orchestrator.generate_creative_plan(record.project_id)
    assert record.status == ProjectStatus.WAITING_STORYBOARD_APPROVAL

    first_stop.set()
    first_thread.join(timeout=15)

    second_ready, second_stop = threading.Event(), threading.Event()
    second_thread = threading.Thread(target=_serve, args=(stack.lifecycle, second_stop, second_ready), daemon=True)
    second_thread.start()
    try:
        assert second_ready.wait(timeout=15)
        record = orchestrator.approve_storyboard(record.project_id)
        assert record.status == ProjectStatus.WAITING_RENDER_APPROVAL
        record = orchestrator.approve_render_plan(record.project_id)
        assert record.status == ProjectStatus.APPROVED
        record = orchestrator.generate_video(record.project_id)
        assert record.status == ProjectStatus.COMPLETED
    finally:
        second_stop.set()
        second_thread.join(timeout=15)
