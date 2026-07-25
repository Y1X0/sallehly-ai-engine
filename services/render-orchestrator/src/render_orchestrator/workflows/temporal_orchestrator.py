"""TemporalProjectOrchestrator: the durable IProjectOrchestrator driver
promised since ADR 0010 and delivered in Phase 8 WP6 - see
docs/adr/0015-temporal-activation.md.

`IProjectOrchestrator`'s nine methods are all plain synchronous calls
(matching `SyncProjectOrchestrator`, matching `ProjectLifecycle`
underneath it), but `temporalio.client.Client` is asyncio-native - the
Python SDK offers no sync client. Each method here bridges with a
private `asyncio.run(...)` per call, reusing one already-connected
`Client` instance across calls. This is deliberately proven safe, not
assumed: a real live Temporal dev server plus a real worker running in
a background thread was used to confirm a single `Client` tolerates
being driven from a fresh event loop on every call (see
tests/test_temporal_orchestrator.py) - the concern being that
`Client.connect()` itself is async and its underlying connection object
could plausibly have been loop-bound the way some pure-Python asyncio
primitives are; it isn't (the connection is backed by the SDK's own
Rust/Tokio bridge, independent of whichever Python event loop happens
to be driving a given call).

`create_project` is the one method with no matching `@workflow.update`
- CreateProjectInput.project_id is generated here (this is now the only
piece of `ProjectLifecycle.create_project`'s id-generation Phase 8 made
overridable) and used as both the Temporal workflow id (giving
"can't create two projects with the same id" for free via Temporal's
own duplicate-workflow-id rejection) and the actual ProjectRecord id.
`Client.execute_update_with_start_workflow` starts the workflow and
runs its `create_project` update as one atomic call, so this method
still returns a fully populated `ProjectRecord` synchronously like
every other `IProjectOrchestrator` implementation must.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from observability import get_logger
from persistence import ProjectRecord
from temporalio.client import (
    Client,
    WithStartWorkflowOperation,
    WorkflowHandle,
    WorkflowUpdateFailedError,
)
from temporalio.common import WorkflowIDConflictPolicy
from temporalio.exceptions import ApplicationError

from ..orchestrator import IProjectOrchestrator
from ..project_lifecycle import ProjectLifecycleError
from .activities import CreateProjectInput
from .render_workflow import ProjectGenerationWorkflow, RenderRejection

_logger = get_logger(__name__)


class TemporalProjectOrchestrator(IProjectOrchestrator):
    """Durable, crash-resumable driver of `ProjectGenerationWorkflow`.
    Same method signatures as `SyncProjectOrchestrator` - `apps/api`'s
    route handlers do not change when this is selected instead (see
    `ORCHESTRATOR=temporal` in `apps/api/state.py`, config_sdk.Settings).
    """

    def __init__(self, client: Client, task_queue: str) -> None:
        self._client = client
        self._task_queue = task_queue

    def create_project(
        self,
        workspace_id: str,
        created_by: str,
        prompt: str,
        target_duration_sec: float,
        aspect_ratio: str,
        reference_asset_ids: list[str] | None = None,
        style_preset_id: str | None = None,
    ) -> ProjectRecord:
        project_id = f"proj_{uuid.uuid4().hex[:12]}"

        async def _run() -> dict[str, Any]:
            op = WithStartWorkflowOperation(
                ProjectGenerationWorkflow.run,
                id=project_id,
                task_queue=self._task_queue,
                id_conflict_policy=WorkflowIDConflictPolicy.FAIL,
            )
            return await self._client.execute_update_with_start_workflow(
                ProjectGenerationWorkflow.create_project,
                CreateProjectInput(
                    project_id=project_id,
                    workspace_id=workspace_id,
                    created_by=created_by,
                    prompt=prompt,
                    target_duration_sec=target_duration_sec,
                    aspect_ratio=aspect_ratio,
                    reference_asset_ids=reference_asset_ids,
                    style_preset_id=style_preset_id,
                ),
                start_workflow_operation=op,
            )

        return ProjectRecord.from_dict(self._run_update(_run()))

    def generate_creative_plan(self, project_id: str) -> ProjectRecord:
        return self._update(project_id, ProjectGenerationWorkflow.generate_creative_plan)

    def approve_storyboard(self, project_id: str) -> ProjectRecord:
        return self._update(project_id, ProjectGenerationWorkflow.approve_storyboard)

    def reject_storyboard(self, project_id: str, feedback: list[str]) -> ProjectRecord:
        return self._update(project_id, ProjectGenerationWorkflow.reject_storyboard, feedback)

    def approve_render_plan(self, project_id: str) -> ProjectRecord:
        return self._update(project_id, ProjectGenerationWorkflow.approve_render_plan)

    def reject_render_plan(
        self, project_id: str, feedback: list[str], quality_tier: str | None = None
    ) -> ProjectRecord:
        rejection = RenderRejection(feedback=feedback, quality_tier=quality_tier)
        return self._update(project_id, ProjectGenerationWorkflow.reject_render_plan, rejection)

    def generate_video(self, project_id: str) -> ProjectRecord:
        return self._update(project_id, ProjectGenerationWorkflow.generate_video)

    def retry_generation(self, project_id: str) -> ProjectRecord:
        return self._update(project_id, ProjectGenerationWorkflow.retry_generation)

    def finalize_project(self, project_id: str, export_spec: dict[str, Any] | None = None) -> ProjectRecord:
        return self._update(project_id, ProjectGenerationWorkflow.finalize_project, export_spec)

    def _update(self, project_id: str, update_method: Any, *args: Any) -> ProjectRecord:
        async def _run() -> dict[str, Any]:
            handle: WorkflowHandle = self._client.get_workflow_handle(project_id)
            return await handle.execute_update(update_method, args=list(args))

        return ProjectRecord.from_dict(self._run_update(_run()))

    def _run_update(self, coro: Any) -> dict[str, Any]:
        """Runs one Temporal RPC to completion and re-raises a failed
        update's original `ProjectLifecycleError` - not the SDK's own
        `WorkflowUpdateFailedError` wrapper - so `apps/api`'s existing
        `except ProjectLifecycleError` handling (409 responses) and
        every test written against `SyncProjectOrchestrator`'s exception
        behavior keep working unchanged regardless of which orchestrator
        is selected. Confirmed empirically (not assumed) that a failed
        activity surfaces to `execute_update` as
        `WorkflowUpdateFailedError` whose `.cause` is an `ActivityError`
        whose own `.cause` is the `ApplicationError` carrying the
        original exception's class name (`.type`) and message
        (`.message`)."""
        try:
            return asyncio.run(coro)
        except WorkflowUpdateFailedError as exc:
            original = _unwrap_application_error(exc)
            if original is not None and original.type == "ProjectLifecycleError":
                _logger.warning(
                    "temporal_update_rejected", extra={"reason": original.message}
                )
                raise ProjectLifecycleError(original.message) from exc
            _logger.error(
                "temporal_update_failed_unexpectedly",
                extra={"application_error_type": original.type if original is not None else None},
            )
            raise


def _unwrap_application_error(exc: BaseException) -> ApplicationError | None:
    seen: list[int] = []
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.append(id(current))
        if isinstance(current, ApplicationError):
            return current
        current = getattr(current, "cause", None)
    return None
