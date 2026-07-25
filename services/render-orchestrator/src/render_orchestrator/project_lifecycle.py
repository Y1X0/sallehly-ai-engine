from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from ai_director import CreativeDirector, ProjectBrief
from creative_compiler import CreativeCompiler
from director_memory import IDirectorMemoryStore
from observability import get_logger, traced_span
from observability.metrics import GENERATION_JOB_DURATION_SECONDS, GENERATION_JOBS_TOTAL, time_histogram
from persistence import IProjectStore, ProjectRecord, ProjectStatus
from quota_sdk import QuotaExceededError

from .events import Event, EventType, IEventBus, InMemoryEventBus
from .jobs import GenerationJobStatus
from .pipeline import GenerationPipeline

if TYPE_CHECKING:
    from cinematic_intelligence import CinematicIntelligenceCoordinator
    from quota_sdk import IQuotaEnforcer

    from .post_production import PostProductionRunner

_logger = get_logger(__name__)


class ProjectLifecycleError(Exception):
    """Raised when a requested transition isn't valid for the project's
    current status (e.g. approving a storyboard that isn't awaiting
    approval), or the project/artifact doesn't exist."""


class ProjectLifecycle:
    """The step implementations behind the full project lifecycle:

        Project Created -> Creative Planning -> Storyboard Approval Gate
                         -> Cinematic Intelligence Layer (prompt/continuity
                            enrichment of the compiled RenderSpecs)
                         -> Render Plan Approval Gate -> Generation Job
                         -> GPU Generation -> Asset Processing -> Completion
                         -> [optional] Post-Processing -> Export -> Exported

    This is the ONE place this logic lives. Both the Temporal workflow
    (workflows/, durable, production) and ProjectOrchestrator
    (orchestrator.py, synchronous, local dev/testing) call these same
    methods - see docs/adr/0010-persistence-and-lifecycle.md for why the
    logic isn't duplicated between the two.

    Does not import or know about Wan2.1/RunPod/Claude specifically:
    CreativeDirector, CreativeCompiler, and GenerationPipeline are
    injected already configured with whatever concrete providers are
    active (see ADR 0001, 0002, 0009) - this class only calls the
    provider-agnostic methods those three already exposed in Phases 1-3.
    Same pattern for `cinematic_intelligence`/`post_production` (Phase 8,
    ADR 0014): both optional, both only ever called through their
    already-tested public methods. Neither is required - a
    `ProjectLifecycle` built without them (as every Phase 4-7 test still
    does) behaves exactly as it always has.
    """

    def __init__(
        self,
        creative_director: CreativeDirector,
        creative_compiler: CreativeCompiler,
        generation_pipeline: GenerationPipeline,
        project_store: IProjectStore,
        memory: IDirectorMemoryStore,
        event_bus: IEventBus | None = None,
        cinematic_intelligence: "CinematicIntelligenceCoordinator | None" = None,
        post_production: "PostProductionRunner | None" = None,
        quota_enforcer: "IQuotaEnforcer | None" = None,
        max_concurrent_generations_per_workspace: int = 0,
    ) -> None:
        self._director = creative_director
        self._compiler = creative_compiler
        self._pipeline = generation_pipeline
        self._projects = project_store
        self._memory = memory
        self._events = event_bus or InMemoryEventBus()
        self._quota = quota_enforcer
        self._max_concurrent_generations = max_concurrent_generations_per_workspace
        self._cinematic = cinematic_intelligence
        self._post_production = post_production

    def create_project(
        self,
        workspace_id: str,
        created_by: str,
        prompt: str,
        target_duration_sec: float,
        aspect_ratio: str,
        reference_asset_ids: list[str] | None = None,
        style_preset_id: str | None = None,
        project_id: str | None = None,
    ) -> ProjectRecord:
        """`project_id` is normally left unset (generated here) - every
        Phase 4-7 caller does this. `TemporalProjectOrchestrator`
        (Phase 8 WP6) is the one caller that supplies its own: it must
        know the id *before* calling Temporal, since it uses it as the
        workflow id (natural create-project idempotency via Temporal's
        own duplicate-workflow-id rejection)."""
        record = ProjectRecord(
            project_id=project_id or f"proj_{uuid.uuid4().hex[:12]}",
            workspace_id=workspace_id,
            created_by=created_by,
            brief={
                "prompt": prompt,
                "target_duration_sec": target_duration_sec,
                "aspect_ratio": aspect_ratio,
                "reference_asset_ids": reference_asset_ids or [],
                "style_preset_id": style_preset_id,
            },
            status=ProjectStatus.CREATED,
        )
        self._projects.create(record)
        self._publish(EventType.PROJECT_CREATED, record.project_id)
        return record

    def generate_creative_plan(self, project_id: str) -> ProjectRecord:
        record = self._require(project_id)
        self._transition(record, ProjectStatus.PLANNING)

        brief = ProjectBrief(
            project_id=project_id,
            prompt=record.brief["prompt"],
            target_duration_sec=record.brief["target_duration_sec"],
            aspect_ratio=record.brief["aspect_ratio"],
            reference_asset_ids=record.brief.get("reference_asset_ids") or None,
            style_preset_id=record.brief.get("style_preset_id"),
        )
        director_plan = self._director.generate_director_plan(brief)
        self._publish(EventType.PLAN_GENERATED, project_id, {"logline": director_plan["logline"]})

        _, storyboard = self._compiler.compile_storyboard(director_plan)
        self._publish(EventType.STORYBOARD_READY, project_id, {"frame_count": len(storyboard["frames"])})

        self._transition(record, ProjectStatus.WAITING_STORYBOARD_APPROVAL)
        return record

    def approve_storyboard(self, project_id: str) -> ProjectRecord:
        record = self._require(project_id, expected=ProjectStatus.WAITING_STORYBOARD_APPROVAL)

        storyboard = self._latest("storyboard", project_id)
        self._compiler.approve_storyboard(project_id, storyboard)

        render_plan = self._compiler.compile_render_plan(project_id)
        self._enrich_render_plan(project_id, render_plan)
        self._publish(EventType.RENDER_READY, project_id, {"shot_count": len(render_plan["render_specs"])})

        self._transition(record, ProjectStatus.WAITING_RENDER_APPROVAL)
        return record

    def _enrich_render_plan(self, project_id: str, render_plan: dict[str, Any]) -> None:
        """Runs the Cinematic Intelligence Layer (Phase 7/8, ADR 0014)
        against the just-compiled RenderPlan, patching its RenderSpecs'
        positive_prompt/negative_prompt in place with CIL-built prompts
        before a human ever sees them for approval (gate 2). A no-op if
        no CinematicIntelligenceCoordinator was injected - see the class
        docstring."""
        if self._cinematic is None:
            return
        director_plan = self._latest("director_plan_enriched", project_id)
        self._cinematic.enrich_render_plan(director_plan, render_plan)

    def reject_storyboard(self, project_id: str, feedback: list[str]) -> ProjectRecord:
        record = self._require(project_id, expected=ProjectStatus.WAITING_STORYBOARD_APPROVAL)

        storyboard = self._latest("storyboard", project_id)
        self._compiler.request_storyboard_changes(
            project_id, storyboard, feedback=[{"comment": item} for item in feedback]
        )
        record.rejected_stage = "storyboard"
        self._transition(record, ProjectStatus.REJECTED)

        director_plan = self._director.regenerate_with_feedback(project_id, feedback)
        self._publish(
            EventType.PLAN_GENERATED, project_id, {"logline": director_plan["logline"], "revision": True}
        )

        _, new_storyboard = self._compiler.compile_storyboard(director_plan)
        self._publish(
            EventType.STORYBOARD_READY,
            project_id,
            {"frame_count": len(new_storyboard["frames"]), "revision": True},
        )

        record.rejected_stage = None
        self._transition(record, ProjectStatus.WAITING_STORYBOARD_APPROVAL)
        return record

    def approve_render_plan(self, project_id: str) -> ProjectRecord:
        record = self._require(project_id, expected=ProjectStatus.WAITING_RENDER_APPROVAL)

        render_plan = self._latest("render_plan", project_id)
        self._compiler.approve_render_plan(project_id, render_plan)

        self._transition(record, ProjectStatus.APPROVED)
        return record

    def reject_render_plan(
        self, project_id: str, feedback: list[str], quality_tier: str | None = None
    ) -> ProjectRecord:
        record = self._require(project_id, expected=ProjectStatus.WAITING_RENDER_APPROVAL)

        render_plan = self._latest("render_plan", project_id)
        self._compiler.request_render_plan_changes(
            project_id, render_plan, feedback=[{"comment": item} for item in feedback]
        )
        record.rejected_stage = "render_plan"
        self._transition(record, ProjectStatus.REJECTED)

        kwargs = {"quality_tier": quality_tier} if quality_tier else {}
        new_render_plan = self._compiler.compile_render_plan(project_id, **kwargs)
        self._enrich_render_plan(project_id, new_render_plan)
        self._publish(
            EventType.RENDER_READY,
            project_id,
            {"shot_count": len(new_render_plan["render_specs"]), "revision": True},
        )

        record.rejected_stage = None
        self._transition(record, ProjectStatus.WAITING_RENDER_APPROVAL)
        return record

    def generate_video(self, project_id: str) -> ProjectRecord:
        record = self._require(project_id, expected=ProjectStatus.APPROVED)
        return self._run_generation(record)

    def retry_generation(self, project_id: str) -> ProjectRecord:
        """Re-runs generation for a project whose previous attempt ended
        in FAILED, against the same already-approved render plan (no
        re-approval needed - approval covers the creative content, not
        the GPU job outcome)."""
        record = self._require(project_id, expected=ProjectStatus.FAILED)
        record.error_message = None
        return self._run_generation(record)

    def finalize_project(self, project_id: str, export_spec: dict[str, Any] | None = None) -> ProjectRecord:
        """Assembles every generated shot into one exported deliverable
        (services/post-processing -> services/export-service, ADR 0012)
        - an explicit, separately-triggered step past COMPLETED, never
        run automatically by generate_video. Requires a
        PostProductionRunner to have been injected (see the class
        docstring); requires `ffmpeg`/`ffprobe` on `PATH` (ADR 0012)."""
        record = self._require(project_id, expected=ProjectStatus.COMPLETED)
        if self._post_production is None:
            raise ProjectLifecycleError("No PostProductionRunner configured for this ProjectLifecycle")

        self._transition(record, ProjectStatus.POST_PROCESSING)
        self._publish(EventType.POST_PROCESSING_STARTED, project_id)

        director_plan = self._latest("director_plan_enriched", project_id)
        render_plan = self._latest("render_plan", project_id)

        try:
            manifest = self._post_production.finalize(director_plan, render_plan, export_spec)
        except Exception as exc:  # noqa: BLE001 - any post-production failure lands here
            record.error_message = str(exc)
            self._transition(record, ProjectStatus.COMPLETED)
            self._publish(EventType.EXPORT_FAILED, project_id, {"error": str(exc)})
            raise ProjectLifecycleError(f"Finalize failed for project {project_id}: {exc}") from exc

        record.render_manifest = manifest
        record.error_message = None
        self._transition(record, ProjectStatus.EXPORTED)
        self._publish(EventType.EXPORT_COMPLETED, project_id, {"manifest_id": manifest.get("manifest_id")})
        return record

    def _run_generation(self, record: ProjectRecord) -> ProjectRecord:
        project_id = record.project_id
        quota_enforced = self._quota is not None and self._max_concurrent_generations > 0
        if quota_enforced:
            try:
                self._quota.acquire(record.workspace_id, max_concurrent=self._max_concurrent_generations)
            except QuotaExceededError as exc:
                # Rejected before any state transition - the project
                # stays exactly where it was (APPROVED or FAILED), safe
                # to retry once capacity frees up, matching every other
                # ProjectLifecycleError's "nothing happened" semantics.
                raise ProjectLifecycleError(str(exc)) from exc

        try:
            self._transition(record, ProjectStatus.GENERATING)
            self._publish(EventType.GENERATION_STARTED, project_id)

            render_plan = self._latest("render_plan", project_id)
            with traced_span("project_lifecycle.run_generation", project_id=project_id):
                with time_histogram(GENERATION_JOB_DURATION_SECONDS):
                    jobs = self._pipeline.generate_plan(render_plan)

            record.generation_job_ids = [job.job_id for job in jobs]
            record.asset_ids = [job.output_asset_id for job in jobs if job.output_asset_id]

            failed = [job for job in jobs if job.status == GenerationJobStatus.FAILED]
            if failed:
                record.error_message = "; ".join(job.error_message or "unknown error" for job in failed)
                self._transition(record, ProjectStatus.FAILED)
                GENERATION_JOBS_TOTAL.labels(status="failed").inc(len(failed))
                GENERATION_JOBS_TOTAL.labels(status="completed").inc(len(jobs) - len(failed))
                self._publish(
                    EventType.GENERATION_FAILED, project_id, {"failed_shot_ids": [job.shot_id for job in failed]}
                )
            else:
                self._transition(record, ProjectStatus.COMPLETED)
                GENERATION_JOBS_TOTAL.labels(status="completed").inc(len(jobs))
                self._publish(EventType.GENERATION_COMPLETED, project_id, {"asset_ids": record.asset_ids})

            return record
        finally:
            if quota_enforced:
                self._quota.release(record.workspace_id)

    def _require(self, project_id: str, expected: ProjectStatus | None = None) -> ProjectRecord:
        record = self._projects.get(project_id)
        if record is None:
            raise ProjectLifecycleError(f"No such project: {project_id}")
        if expected is not None and record.status != expected:
            raise ProjectLifecycleError(
                f"Project {project_id} is {record.status.value}, expected {expected.value}"
            )
        return record

    def _latest(self, stage: str, project_id: str) -> dict[str, Any]:
        entry = self._memory.latest(project_id, stage)
        if entry is None:
            raise ProjectLifecycleError(f"No {stage} found for project {project_id}")
        return entry.content

    def _transition(self, record: ProjectRecord, status: ProjectStatus) -> None:
        record.status = status
        self._projects.save(record)

    def _publish(self, event_type: EventType, project_id: str, data: dict[str, Any] | None = None) -> None:
        """Every meaningful ProjectLifecycle transition already funnels
        through here (see every call site above) - the single, minimal
        integration point for structured logging (Phase 8 WP1) rather
        than a separate log call sprinkled into each of the nine public
        methods. Additive only: the `IEventBus.publish()` call and its
        behavior are completely unchanged."""
        data = data or {}
        _logger.info(event_type.value, extra={"project_id": project_id, **data})
        self._events.publish(Event(type=event_type, project_id=project_id, data=data))
