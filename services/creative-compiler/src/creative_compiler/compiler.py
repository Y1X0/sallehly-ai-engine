from __future__ import annotations

import copy
import time
from typing import Any

import schemas
from camera_engine import CameraDirector
from director_memory import DirectorMemoryEntry, IDirectorMemoryStore, InMemoryDirectorMemoryStore
from lighting_engine import LightingDirector
from motion_engine import MotionDirector
from render_config_compiler import RenderConfigCompiler
from storyboard_generator import StoryboardGenerator
from style_engine import StyleDirector
from video_engine_sdk import CapabilityManifest


class CreativeCompiler:
    """Orchestrates the Phase 2 Creative Compiler pipeline:

        DirectorPlan (bare shots, from CreativeDirector)
          -> Camera/Motion/Lighting/Style Directors (per shot)
          -> Storyboard Generator
               === approval gate 1: storyboard ===
          -> Render Specification Generator
               === approval gate 2: render plan ===

    Mirrors CreativeDirector's shape (Phase 1): compose deterministic
    stages, assemble + validate, record every artifact in DirectorMemory.
    Re-planning after `changes_requested` feedback (looping back to
    CreativeDirector.regenerate_with_feedback and then back through this
    class) is an orchestration concern owned by the Render Orchestrator
    (Phase 4, Temporal) - this class only produces artifacts and records
    approval/rejection state, it does not drive the retry loop itself.
    """

    def __init__(
        self,
        capability_manifest: CapabilityManifest,
        memory: IDirectorMemoryStore | None = None,
    ) -> None:
        self._camera_director = CameraDirector()
        self._motion_director = MotionDirector()
        self._lighting_director = LightingDirector()
        self._style_director = StyleDirector()
        self._storyboard_generator = StoryboardGenerator()
        self._render_config_compiler = RenderConfigCompiler()
        self._capability_manifest = capability_manifest
        self._memory = memory or InMemoryDirectorMemoryStore()

    def compile_storyboard(self, director_plan: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        plan = copy.deepcopy(director_plan)
        plan["global_style"] = self._style_director.finalize_global_style(plan)

        for scene in plan["scenes"]:
            shots = scene["shots"]
            total = len(shots)
            for index, shot in enumerate(shots):
                position = self._camera_director.position_for(index, total)
                shot["camera"] = self._camera_director.plan_camera(shot, position)
                shot["motion"] = self._motion_director.plan_motion(shot, shot["camera"])
                shot["lighting"] = self._lighting_director.plan_lighting(
                    shot, shot["camera"], plan["global_style"]
                )

        schemas.validate(plan, "director_plan")

        storyboard = self._storyboard_generator.generate(plan)
        schemas.validate(storyboard, "storyboard")

        self._remember(plan["project_id"], "director_plan_enriched", plan)
        self._remember(plan["project_id"], "storyboard", storyboard)
        return plan, storyboard

    def approve_storyboard(self, project_id: str, storyboard: dict[str, Any]) -> dict[str, Any]:
        approved = {**storyboard, "status": "approved"}
        self._remember(project_id, "storyboard", approved)
        return approved

    def request_storyboard_changes(
        self, project_id: str, storyboard: dict[str, Any], feedback: list[dict[str, Any]]
    ) -> dict[str, Any]:
        rejected = {**storyboard, "status": "changes_requested", "reviewer_feedback": feedback}
        self._remember(project_id, "storyboard", rejected)
        return rejected

    def compile_render_plan(self, project_id: str, quality_tier: str = "final") -> dict[str, Any]:
        storyboard_entry = self._memory.latest(project_id, "storyboard")
        plan_entry = self._memory.latest(project_id, "director_plan_enriched")
        if storyboard_entry is None or plan_entry is None:
            raise ValueError(f"No storyboard/enriched DirectorPlan in memory for project {project_id}")
        if storyboard_entry.content.get("status") != "approved":
            raise ValueError("Storyboard must be approved (gate 1) before compiling a render plan")

        director_plan = plan_entry.content
        render_specs = self._render_config_compiler.compile(
            director_plan, self._capability_manifest, quality_tier=quality_tier
        )

        render_plan = {
            "project_id": project_id,
            "director_plan_version": schemas.content_hash(director_plan),
            "engine_id": self._capability_manifest.engine_id,
            "status": "pending_review",
            "render_specs": render_specs,
        }
        schemas.validate(render_plan, "render_plan")

        self._remember(project_id, "render_plan", render_plan)
        return render_plan

    def approve_render_plan(self, project_id: str, render_plan: dict[str, Any]) -> dict[str, Any]:
        approved = {**render_plan, "status": "approved"}
        self._remember(project_id, "render_plan", approved)
        return approved

    def request_render_plan_changes(
        self, project_id: str, render_plan: dict[str, Any], feedback: list[dict[str, Any]]
    ) -> dict[str, Any]:
        rejected = {**render_plan, "status": "changes_requested", "reviewer_feedback": feedback}
        self._remember(project_id, "render_plan", rejected)
        return rejected

    def _remember(self, project_id: str, stage: str, content: dict[str, Any]) -> None:
        self._memory.append(
            project_id, DirectorMemoryEntry(stage=stage, content=content, created_at=time.time())
        )
