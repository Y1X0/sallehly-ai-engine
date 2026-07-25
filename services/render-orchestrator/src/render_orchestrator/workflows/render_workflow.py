"""Temporal workflow definition. See docs/workflows/ai-director-workflow.md
for the sequence diagram, docs/adr/0010-persistence-and-lifecycle.md for
why this exists alongside the synchronous SyncProjectOrchestrator, and
docs/adr/0015-temporal-activation.md for the Phase 8 (WP6) redesign this
file went through - see that ADR's "Workflow shape: signals to updates"
decision for why every gated action below is a `@workflow.update`
rather than the original `@workflow.signal` + auto-chained `run()` this
file used before WP6.

This package (render_orchestrator.workflows) is the only place in the
codebase allowed to import the Temporal SDK - every activity it calls
out to (activities.py) talks to ProjectLifecycle, which itself only
talks to CreativeDirector/CreativeCompiler/GenerationPipeline through
their existing interfaces. Nothing about ADR 0001/0002's boundaries
changes here.

Genuinely executed as of Phase 8 WP6 (ADR 0015) - a real `temporal`
CLI dev server plus a real worker running this exact workflow
definition, driven by TemporalProjectOrchestrator, not just
structurally validated against the SDK's decorators as it was before.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

from .activities import (
    CreateProjectInput,
    FinalizeProjectInput,
    ProjectActivities,
    RejectRenderPlanInput,
    RejectStoryboardInput,
)

# Every activity call below sets non_retryable_error_types=["ProjectLifecycleError"]
# - genuinely necessary, not defensive decoration: Temporal's own
# default RetryPolicy (used whenever one isn't given explicitly) retries
# indefinitely with backoff, and ProjectLifecycleError (e.g. "approving
# a storyboard that isn't waiting_storyboard_approval") is a permanent,
# not transient, failure - retrying it fails identically forever, which
# means the calling update() RPC (and therefore the synchronous
# IProjectOrchestrator.* caller on the other end - apps/api's request
# thread) would simply hang rather than getting the same immediate
# ProjectLifecycleError SyncProjectOrchestrator raises. This was a real
# bug caught by actually running these updates for the first time in
# Phase 8 WP6 (ADR 0015), not a hypothetical concern - the "wrong state
# transition" test genuinely hung until this was added.
_NON_RETRYABLE = ["ProjectLifecycleError"]
_DEFAULT_RETRY_POLICY = RetryPolicy(maximum_attempts=3, non_retryable_error_types=_NON_RETRYABLE)
_SINGLE_ATTEMPT_RETRY_POLICY = RetryPolicy(maximum_attempts=1, non_retryable_error_types=_NON_RETRYABLE)
_GENERATION_RETRY_POLICY = RetryPolicy(maximum_attempts=2, non_retryable_error_types=_NON_RETRYABLE)


@dataclass
class RenderRejection:
    feedback: list[str] = field(default_factory=list)
    quality_tier: str | None = None


@workflow.defn
class ProjectGenerationWorkflow:
    """Durable counterpart to ProjectLifecycle's flow:

        Project Created -> Creative Planning -> Storyboard Approval Gate
                         -> Render Plan Approval Gate -> Generation Job
                         -> GPU Generation -> Asset Processing -> Completion
                         -> [optional] Post-Processing -> Export

    One workflow execution == one project's entire durable state
    machine, from creation through an optional `finalize_project` call
    that may happen much later. Every `IProjectOrchestrator` method has
    a matching `@workflow.update` here (`create_project` is the one
    exception - it is folded into workflow start via
    `Client.execute_update_with_start_workflow`, see
    TemporalProjectOrchestrator) - a client calls exactly the update
    that matches the action a human just took and gets the resulting
    ProjectRecord dict back synchronously, while the workflow's durable
    event history is what survives a worker crash and resumes exactly
    where it left off (which a plain synchronous call graph cannot do
    on its own).

    The workflow intentionally never self-terminates except once a
    project reaches EXPORTED - retry_generation/finalize_project can
    both be called an arbitrary amount of time after generate_video
    finishes, so the workflow must stay open and responsive to updates
    until there is truly nothing left a caller could still do. A
    project that's simply abandoned at FAILED/COMPLETED (nobody ever
    calls retry_generation/finalize_project) leaves its workflow open
    indefinitely - a known, documented limitation (see ADR 0015's
    Consequences), not addressed by this pass (a TTL-based auto-close
    or continue-as-new policy would be the production hardening
    follow-up).
    """

    def __init__(self) -> None:
        self._project_id: str | None = None
        self._status: str = "created"
        self._closed = False

    @workflow.run
    async def run(self) -> dict[str, Any]:
        await workflow.wait_condition(lambda: self._closed)
        return {"project_id": self._project_id, "status": self._status}

    @workflow.update
    async def create_project(self, input: CreateProjectInput) -> dict[str, Any]:
        record = await workflow.execute_activity(
            ProjectActivities.create_project,
            input,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=_SINGLE_ATTEMPT_RETRY_POLICY,
        )
        self._project_id = record["project_id"]
        self._status = record["status"]
        return record

    @workflow.update
    async def generate_creative_plan(self) -> dict[str, Any]:
        record = await workflow.execute_activity(
            ProjectActivities.generate_creative_plan,
            self._project_id,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=_DEFAULT_RETRY_POLICY,
        )
        self._status = record["status"]
        return record

    @workflow.update
    async def approve_storyboard(self) -> dict[str, Any]:
        record = await workflow.execute_activity(
            ProjectActivities.approve_storyboard,
            self._project_id,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=_SINGLE_ATTEMPT_RETRY_POLICY,
        )
        self._status = record["status"]
        return record

    @workflow.update
    async def reject_storyboard(self, feedback: list[str]) -> dict[str, Any]:
        record = await workflow.execute_activity(
            ProjectActivities.reject_storyboard,
            RejectStoryboardInput(project_id=self._project_id, feedback=feedback),
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=_DEFAULT_RETRY_POLICY,
        )
        self._status = record["status"]
        return record

    @workflow.update
    async def approve_render_plan(self) -> dict[str, Any]:
        record = await workflow.execute_activity(
            ProjectActivities.approve_render_plan,
            self._project_id,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=_SINGLE_ATTEMPT_RETRY_POLICY,
        )
        self._status = record["status"]
        return record

    @workflow.update
    async def reject_render_plan(self, rejection: RenderRejection) -> dict[str, Any]:
        record = await workflow.execute_activity(
            ProjectActivities.reject_render_plan,
            RejectRenderPlanInput(
                project_id=self._project_id,
                feedback=rejection.feedback,
                quality_tier=rejection.quality_tier,
            ),
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=_DEFAULT_RETRY_POLICY,
        )
        self._status = record["status"]
        return record

    @workflow.update
    async def generate_video(self) -> dict[str, Any]:
        record = await workflow.execute_activity(
            ProjectActivities.generate_video,
            self._project_id,
            start_to_close_timeout=timedelta(hours=1),
            retry_policy=_GENERATION_RETRY_POLICY,
        )
        self._status = record["status"]
        return record

    @workflow.update
    async def retry_generation(self) -> dict[str, Any]:
        record = await workflow.execute_activity(
            ProjectActivities.retry_generation,
            self._project_id,
            start_to_close_timeout=timedelta(hours=1),
            retry_policy=_GENERATION_RETRY_POLICY,
        )
        self._status = record["status"]
        return record

    @workflow.update
    async def finalize_project(self, export_spec: dict[str, Any] | None) -> dict[str, Any]:
        record = await workflow.execute_activity(
            ProjectActivities.finalize_project,
            FinalizeProjectInput(project_id=self._project_id, export_spec=export_spec),
            start_to_close_timeout=timedelta(minutes=30),
            retry_policy=_GENERATION_RETRY_POLICY,
        )
        self._status = record["status"]
        if record["status"] == "exported":
            self._closed = True
        return record

    @workflow.query
    def status(self) -> str:
        return self._status

    @workflow.query
    def project_id(self) -> str | None:
        return self._project_id
