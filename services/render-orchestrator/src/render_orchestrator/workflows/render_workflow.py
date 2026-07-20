"""Temporal workflow definition. See docs/workflows/ai-director-workflow.md
for the sequence diagram and docs/adr/0010-persistence-and-lifecycle.md
for why this exists alongside the synchronous SyncProjectOrchestrator.

This package (render_orchestrator.workflows) is the only place in the
codebase allowed to import the Temporal SDK - every activity it calls
out to (activities.py) talks to ProjectLifecycle, which itself only
talks to CreativeDirector/CreativeCompiler/GenerationPipeline through
their existing interfaces. Nothing about ADR 0001/0002's boundaries
changes here.

NOT executable in this environment: temporalio's ephemeral test server
(temporalio.testing.WorkflowEnvironment) downloads a native binary from
temporal.download on first use, which this sandbox's network policy
blocks - the same class of limitation as Phase 3's live GPU inference.
This code is written to the real temporalio SDK and is what a worker
process would run against a real Temporal server
(`docker compose --profile temporal up`, see docs/DEV_SETUP.md);
tests instead exercise ProjectLifecycle/SyncProjectOrchestrator, which
contain 100% of the actual business logic this workflow calls through
activities.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Literal

from temporalio import workflow
from temporalio.common import RetryPolicy

from .activities import (
    CreateProjectInput,
    ProjectActivities,
    RejectRenderPlanInput,
    RejectStoryboardInput,
)

_DEFAULT_RETRY_POLICY = RetryPolicy(maximum_attempts=3)


@dataclass
class ProjectWorkflowInput:
    workspace_id: str
    created_by: str
    prompt: str
    target_duration_sec: float
    aspect_ratio: str
    reference_asset_ids: list[str] | None = None
    style_preset_id: str | None = None


@dataclass
class RenderRejection:
    feedback: list[str] = field(default_factory=list)
    quality_tier: str | None = None


_Decision = Literal["approved", "rejected"]


@workflow.defn
class ProjectGenerationWorkflow:
    """Durable counterpart to ProjectLifecycle's flow:

        Project Created -> Creative Planning -> Storyboard Approval Gate
                         -> Render Plan Approval Gate -> Generation Job
                         -> GPU Generation -> Asset Processing -> Completion

    Approval gates are modeled as signals the workflow blocks on via
    workflow.wait_condition - this is what survives a worker crash and
    resumes exactly where it left off (Temporal's event history replays
    the workflow's state), which a plain synchronous call graph cannot
    do on its own.
    """

    def __init__(self) -> None:
        self._project_id: str | None = None
        self._status: str = "created"
        self._storyboard_decision: _Decision | None = None
        self._storyboard_feedback: list[str] = []
        self._render_decision: _Decision | None = None
        self._render_rejection = RenderRejection()

    @workflow.run
    async def run(self, input: ProjectWorkflowInput) -> dict[str, Any]:
        record = await workflow.execute_activity(
            ProjectActivities.create_project,
            CreateProjectInput(
                workspace_id=input.workspace_id,
                created_by=input.created_by,
                prompt=input.prompt,
                target_duration_sec=input.target_duration_sec,
                aspect_ratio=input.aspect_ratio,
                reference_asset_ids=input.reference_asset_ids,
                style_preset_id=input.style_preset_id,
            ),
            start_to_close_timeout=timedelta(seconds=30),
        )
        self._project_id = record["project_id"]
        self._status = record["status"]

        record = await workflow.execute_activity(
            ProjectActivities.generate_creative_plan,
            self._project_id,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=_DEFAULT_RETRY_POLICY,
        )
        self._status = record["status"]

        record = await self._await_storyboard_approval()
        self._status = record["status"]

        record = await self._await_render_approval()
        self._status = record["status"]

        record = await workflow.execute_activity(
            ProjectActivities.generate_video,
            self._project_id,
            start_to_close_timeout=timedelta(hours=1),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )
        self._status = record["status"]
        return record

    async def _await_storyboard_approval(self) -> dict[str, Any]:
        while True:
            await workflow.wait_condition(lambda: self._storyboard_decision is not None)
            decision, self._storyboard_decision = self._storyboard_decision, None
            if decision == "approved":
                return await workflow.execute_activity(
                    ProjectActivities.approve_storyboard,
                    self._project_id,
                    start_to_close_timeout=timedelta(minutes=5),
                )
            await workflow.execute_activity(
                ProjectActivities.reject_storyboard,
                RejectStoryboardInput(project_id=self._project_id, feedback=self._storyboard_feedback),
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=_DEFAULT_RETRY_POLICY,
            )
            # Loop back: reject_storyboard already regenerated a fresh
            # storyboard and left the project WAITING_STORYBOARD_APPROVAL
            # again, so we wait for the next approve/reject signal on it.

    async def _await_render_approval(self) -> dict[str, Any]:
        while True:
            await workflow.wait_condition(lambda: self._render_decision is not None)
            decision, self._render_decision = self._render_decision, None
            if decision == "approved":
                return await workflow.execute_activity(
                    ProjectActivities.approve_render_plan,
                    self._project_id,
                    start_to_close_timeout=timedelta(minutes=5),
                )
            await workflow.execute_activity(
                ProjectActivities.reject_render_plan,
                RejectRenderPlanInput(
                    project_id=self._project_id,
                    feedback=self._render_rejection.feedback,
                    quality_tier=self._render_rejection.quality_tier,
                ),
                start_to_close_timeout=timedelta(minutes=5),
            )

    @workflow.signal
    async def approve_storyboard(self) -> None:
        self._storyboard_decision = "approved"

    @workflow.signal
    async def reject_storyboard(self, feedback: list[str]) -> None:
        self._storyboard_decision = "rejected"
        self._storyboard_feedback = feedback

    @workflow.signal
    async def approve_render_plan(self) -> None:
        self._render_decision = "approved"

    @workflow.signal
    async def reject_render_plan(self, rejection: RenderRejection) -> None:
        self._render_decision = "rejected"
        self._render_rejection = rejection

    @workflow.query
    def status(self) -> str:
        return self._status

    @workflow.query
    def project_id(self) -> str | None:
        return self._project_id
