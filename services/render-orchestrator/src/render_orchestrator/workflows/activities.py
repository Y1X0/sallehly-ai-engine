"""Temporal activities: thin wrappers around ProjectLifecycle's methods.

Activities are the only place non-deterministic/side-effecting work is
allowed to happen in a Temporal application - the workflow (render_workflow.py)
never calls ProjectLifecycle directly, only through these. Defined as
instance methods (bound to one ProjectActivities holding a concrete,
already-wired ProjectLifecycle) per Temporal's documented multi-activity
class pattern: the workflow references the unbound method
(`ProjectActivities.generate_creative_plan`) for name resolution, while
the Worker is given a bound instance (`activities.generate_creative_plan`)
that actually executes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from temporalio import activity

from ..project_lifecycle import ProjectLifecycle


@dataclass
class CreateProjectInput:
    project_id: str
    workspace_id: str
    created_by: str
    prompt: str
    target_duration_sec: float
    aspect_ratio: str
    reference_asset_ids: list[str] | None = None
    style_preset_id: str | None = None


@dataclass
class RejectStoryboardInput:
    project_id: str
    feedback: list[str]


@dataclass
class RejectRenderPlanInput:
    project_id: str
    feedback: list[str]
    quality_tier: str | None = None


@dataclass
class FinalizeProjectInput:
    project_id: str
    export_spec: dict[str, Any] | None = None


class ProjectActivities:
    def __init__(self, lifecycle: ProjectLifecycle) -> None:
        self._lifecycle = lifecycle

    @activity.defn
    def create_project(self, input: CreateProjectInput) -> dict[str, Any]:
        record = self._lifecycle.create_project(
            workspace_id=input.workspace_id,
            created_by=input.created_by,
            prompt=input.prompt,
            target_duration_sec=input.target_duration_sec,
            aspect_ratio=input.aspect_ratio,
            reference_asset_ids=input.reference_asset_ids,
            style_preset_id=input.style_preset_id,
            project_id=input.project_id,
        )
        return record.to_dict()

    @activity.defn
    def generate_creative_plan(self, project_id: str) -> dict[str, Any]:
        return self._lifecycle.generate_creative_plan(project_id).to_dict()

    @activity.defn
    def approve_storyboard(self, project_id: str) -> dict[str, Any]:
        return self._lifecycle.approve_storyboard(project_id).to_dict()

    @activity.defn
    def reject_storyboard(self, input: RejectStoryboardInput) -> dict[str, Any]:
        return self._lifecycle.reject_storyboard(input.project_id, input.feedback).to_dict()

    @activity.defn
    def approve_render_plan(self, project_id: str) -> dict[str, Any]:
        return self._lifecycle.approve_render_plan(project_id).to_dict()

    @activity.defn
    def reject_render_plan(self, input: RejectRenderPlanInput) -> dict[str, Any]:
        return self._lifecycle.reject_render_plan(
            input.project_id, input.feedback, input.quality_tier
        ).to_dict()

    @activity.defn
    def generate_video(self, project_id: str) -> dict[str, Any]:
        return self._lifecycle.generate_video(project_id).to_dict()

    @activity.defn
    def retry_generation(self, project_id: str) -> dict[str, Any]:
        return self._lifecycle.retry_generation(project_id).to_dict()

    @activity.defn
    def finalize_project(self, input: FinalizeProjectInput) -> dict[str, Any]:
        return self._lifecycle.finalize_project(input.project_id, input.export_spec).to_dict()

    def all_activities(self) -> list[Any]:
        """The bound-method list a Worker registers:
        Worker(..., activities=activities.all_activities())."""
        return [
            self.create_project,
            self.generate_creative_plan,
            self.approve_storyboard,
            self.reject_storyboard,
            self.approve_render_plan,
            self.reject_render_plan,
            self.generate_video,
            self.retry_generation,
            self.finalize_project,
        ]
