"""Builds the temporalio Worker that actually executes
`ProjectGenerationWorkflow`/`ProjectActivities` against a live Temporal
server - the piece ADR 0010 always said a "future TemporalProjectOrchestrator"
would need, delivered in Phase 8 WP6 (docs/adr/0015-temporal-activation.md).

Deliberately takes an already-constructed `ProjectLifecycle` rather than
building one itself - the same "caller wires the concrete providers,
this module only consumes the interface" discipline every other part of
this codebase holds to (ADR 0001/0002). See
`apps/api/src/api/temporal_worker.py` for the standalone process
entrypoint that reuses `apps/api`'s own `build_app_state` wiring so
there is exactly one place that decides which concrete
`ILLMProvider`/`IVideoEngine`/`IComputeProvider` are active, whether the
worker or the API process reads it.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from temporalio.client import Client
from temporalio.worker import Worker
from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner, SandboxRestrictions

from ..project_lifecycle import ProjectLifecycle
from .activities import ProjectActivities
from .render_workflow import ProjectGenerationWorkflow

# render_workflow.py's `from .activities import ...` (needed so
# workflow.execute_activity can reference ProjectActivities.<method> by
# real class/method object, temporalio's recommended - type-safe -
# pattern rather than a bare string) drags in this whole workspace's
# business-logic dependency graph the moment the sandbox re-imports
# render_workflow.py for determinism-checking: render_orchestrator.workflows
# is nested inside render_orchestrator, so Python always runs
# render_orchestrator/__init__.py first, which eagerly imports
# ProjectLifecycle -> CreativeDirector -> CreativeCompiler -> ... -
# every first-party package in this monorepo, transitively. Several of
# them (packages/schemas, packages/prompt-engine, ...) do a one-time
# `Path(__file__).resolve()` at import time to locate a data directory -
# genuinely deterministic in practice (a fixed, package-relative path,
# no external state) but the sandbox can't know that and correctly
# refuses any filesystem call by default.
#
# None of this business logic ever actually *executes* inside the
# workflow sandbox at runtime - ProjectActivities/ProjectLifecycle only
# run inside the activity executor's thread pool, outside the sandbox
# entirely (activities are explicitly exempt from the determinism
# requirement, by design - only workflow code needs it). The sandbox
# only re-imports this graph to resolve `ProjectActivities.<method>`
# references at workflow-definition-validation time. So it's correct,
# not just convenient, to pass every first-party workspace package
# through except render_orchestrator itself - the workflow module
# genuinely defined in *this* package is exactly what still needs real
# sandboxed determinism-checking. Discovered by actually running a
# worker for the first time in Phase 8 WP6 (ADR 0015) - the pre-WP6
# "structurally validated only" code never hit this, since nothing had
# ever imported it into a real sandboxed workflow runner before.
_PASSTHROUGH_MODULES = {
    "ai_director",
    "asset_manager",
    "auth",
    "camera_engine",
    "cinematic_intelligence",
    "cinematic_intelligence_sdk",
    "config_sdk",
    "creative_brief_parser",
    "creative_compiler",
    "director_memory",
    "export_service",
    "lighting_engine",
    "llm_providers",
    "motion_engine",
    "observability",
    "persistence",
    "post_processing",
    "prompt_builder",
    "prompt_engine",
    "render_config_compiler",
    "scene_builder",
    "schemas",
    "shot_planner",
    "storage_sdk",
    "story_planner",
    "storyboard_generator",
    "style_engine",
    "video_composition_sdk",
    "video_engine_adapter",
    "video_engine_sdk",
}
_WORKFLOW_RUNNER = SandboxedWorkflowRunner(
    restrictions=SandboxRestrictions.default.with_passthrough_modules(*_PASSTHROUGH_MODULES)
)


def build_worker(client: Client, task_queue: str, lifecycle: ProjectLifecycle) -> Worker:
    """A `Worker` ready to `.run()` (or use as an `async with` context
    manager, e.g. in tests) - hosts `ProjectGenerationWorkflow` and
    every `ProjectActivities` method bound to `lifecycle`.

    `ProjectActivities`' methods are plain `def`, not `async def` (they
    call straight into `ProjectLifecycle`, which is synchronous
    end-to-end, same as every other pre-Phase-8 caller) - the temporalio
    `Worker` requires an explicit `activity_executor` for any non-async
    activity, a requirement genuinely never exercised until Phase 8 WP6
    actually ran this worker for the first time (ADR 0015). A small
    fixed-size thread pool is enough here: `ProjectLifecycle`'s own
    methods are themselves synchronous/blocking end-to-end (they are
    exactly what Phase 8's scale-out plan's WP2/WP3 durable-store work
    is meant to make safe for concurrent access from multiple threads;
    see docs/PHASE8_SCALEOUT_PLAN.md)."""
    activities = ProjectActivities(lifecycle)
    return Worker(
        client,
        task_queue=task_queue,
        workflows=[ProjectGenerationWorkflow],
        activities=activities.all_activities(),
        activity_executor=ThreadPoolExecutor(max_workers=8),
        workflow_runner=_WORKFLOW_RUNNER,
    )
