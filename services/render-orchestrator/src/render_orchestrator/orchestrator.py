from __future__ import annotations

from abc import ABC, abstractmethod

from persistence import ProjectRecord

from .project_lifecycle import ProjectLifecycle


class IProjectOrchestrator(ABC):
    """What apps/api actually depends on - one interface, two possible
    backends:

    - `SyncProjectOrchestrator` (this module): drives `ProjectLifecycle`
      directly and synchronously. What this environment and local dev
      use - see docs/adr/0010-persistence-and-lifecycle.md for why a live
      Temporal server isn't available here (its ephemeral test server
      needs a binary download blocked by this sandbox's network policy,
      same class of limitation as Phase 3's GPU inference).
    - A future `TemporalProjectOrchestrator` would construct/signal a
      real `ProjectGenerationWorkflow` (workflows/render_workflow.py) via
      a `temporalio.client.Client` - same method signatures, so
      `apps/api`'s route handlers never change when that swap happens.
    """

    @abstractmethod
    def create_project(
        self,
        workspace_id: str,
        created_by: str,
        prompt: str,
        target_duration_sec: float,
        aspect_ratio: str,
        reference_asset_ids: list[str] | None = None,
        style_preset_id: str | None = None,
    ) -> ProjectRecord: ...

    @abstractmethod
    def generate_creative_plan(self, project_id: str) -> ProjectRecord: ...

    @abstractmethod
    def approve_storyboard(self, project_id: str) -> ProjectRecord: ...

    @abstractmethod
    def reject_storyboard(self, project_id: str, feedback: list[str]) -> ProjectRecord: ...

    @abstractmethod
    def approve_render_plan(self, project_id: str) -> ProjectRecord: ...

    @abstractmethod
    def reject_render_plan(
        self, project_id: str, feedback: list[str], quality_tier: str | None = None
    ) -> ProjectRecord: ...

    @abstractmethod
    def generate_video(self, project_id: str) -> ProjectRecord: ...


class SyncProjectOrchestrator(IProjectOrchestrator):
    """Synchronous, non-durable driver: each method call runs to
    completion in-process. Fine for this environment/local dev/tests; a
    process crash mid-call loses that call's progress (the whole point
    Temporal's workflow would solve in production - see workflows/).
    """

    def __init__(self, lifecycle: ProjectLifecycle) -> None:
        self._lifecycle = lifecycle

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
        return self._lifecycle.create_project(
            workspace_id, created_by, prompt, target_duration_sec, aspect_ratio,
            reference_asset_ids, style_preset_id,
        )

    def generate_creative_plan(self, project_id: str) -> ProjectRecord:
        return self._lifecycle.generate_creative_plan(project_id)

    def approve_storyboard(self, project_id: str) -> ProjectRecord:
        return self._lifecycle.approve_storyboard(project_id)

    def reject_storyboard(self, project_id: str, feedback: list[str]) -> ProjectRecord:
        return self._lifecycle.reject_storyboard(project_id, feedback)

    def approve_render_plan(self, project_id: str) -> ProjectRecord:
        return self._lifecycle.approve_render_plan(project_id)

    def reject_render_plan(
        self, project_id: str, feedback: list[str], quality_tier: str | None = None
    ) -> ProjectRecord:
        return self._lifecycle.reject_render_plan(project_id, feedback, quality_tier)

    def generate_video(self, project_id: str) -> ProjectRecord:
        return self._lifecycle.generate_video(project_id)

    def run_to_completion(self, project_id: str) -> ProjectRecord:
        """Convenience for local dev/tests: drives a freshly-created
        project through every gate with auto-approval, ending in
        COMPLETED or FAILED. Real usage always goes through the
        individual gated methods above so a human can actually review
        each gate - this is not exposed as its own API endpoint."""
        self.generate_creative_plan(project_id)
        self.approve_storyboard(project_id)
        self.approve_render_plan(project_id)
        return self.generate_video(project_id)
