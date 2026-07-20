from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import jsonschema
from creative_brief_parser import CreativeBriefParser
from director_memory import DirectorMemoryEntry, IDirectorMemoryStore, InMemoryDirectorMemoryStore
from llm_providers import ILLMProvider, RetryingLLMProvider
from llm_providers.errors import SchemaValidationError
from scene_builder import SceneGenerator
import schemas
from shot_planner import ShotPlanner
from story_planner import StoryPlanner

DEFAULT_NEGATIVE_PROMPT = (
    "distorted anatomy, extra limbs, warped faces, flickering, jittery motion, "
    "text, watermark, logo, low quality, blurry"
)


@dataclass(frozen=True)
class ProjectBrief:
    """Mirrors the `brief` object in packages/schemas/json/project.schema.json."""

    project_id: str
    prompt: str
    target_duration_sec: float
    aspect_ratio: str
    reference_asset_ids: list[str] | None = None
    style_preset_id: str | None = None


class CreativeDirector:
    """Orchestrates the full Creative Director pipeline:

        raw idea -> Creative Brief Parser -> Story Planner
                 -> Scene Generator -> Shot Planner -> DirectorPlan

    Everything from a raw idea up to (but not including) the Camera/
    Lighting/Motion/Style Directors and the Render Configuration Compiler
    (Phase 2) lives behind this one entry point. Each stage above is its
    own service with its own ILLMProvider dependency where relevant (see
    docs/adr/0001-director-engine-separation.md) - this class composes
    them and owns the DirectorMemory that makes the storyboard revision
    loop possible (docs/workflows/ai-director-workflow.md).
    """

    def __init__(
        self,
        llm_provider: ILLMProvider,
        memory: IDirectorMemoryStore | None = None,
        max_retries: int = 2,
    ) -> None:
        self._llm = RetryingLLMProvider(llm_provider, max_retries=max_retries)
        self._brief_parser = CreativeBriefParser(self._llm)
        self._story_planner = StoryPlanner(self._llm)
        self._scene_generator = SceneGenerator()
        self._shot_planner = ShotPlanner()
        self._memory = memory or InMemoryDirectorMemoryStore()

    def generate_director_plan(self, brief: ProjectBrief) -> dict[str, Any]:
        creative_brief = self._brief_parser.parse(
            brief.project_id,
            brief.prompt,
            target_duration_sec=brief.target_duration_sec,
            aspect_ratio=brief.aspect_ratio,
        )
        self._remember(brief.project_id, "creative_brief", creative_brief)

        story_outline = self._story_planner.plan(
            creative_brief,
            target_duration_sec=brief.target_duration_sec,
            aspect_ratio=brief.aspect_ratio,
        )
        self._remember(brief.project_id, "story_outline", story_outline)

        director_plan = self._assemble(brief, story_outline)
        self._remember(brief.project_id, "director_plan", director_plan)
        return director_plan

    def regenerate_with_feedback(self, project_id: str, feedback: list[str]) -> dict[str, Any]:
        """Re-invokes the Story Planner with prior context + reviewer
        feedback, per the `changes_requested` branch in
        docs/workflows/ai-director-workflow.md."""
        creative_brief_entry = self._memory.latest(project_id, "creative_brief")
        story_outline_entry = self._memory.latest(project_id, "story_outline")
        director_plan_entry = self._memory.latest(project_id, "director_plan")
        if not (creative_brief_entry and story_outline_entry and director_plan_entry):
            raise ValueError(f"No prior pipeline history found for project {project_id}")

        self._remember(project_id, "feedback", {"feedback": feedback})

        creative_brief = creative_brief_entry.content
        prior_plan = director_plan_entry.content

        story_outline = self._story_planner.plan(
            creative_brief,
            target_duration_sec=prior_plan["target_duration_sec"],
            aspect_ratio=prior_plan["aspect_ratio"],
            feedback=feedback,
            prior_story_outline=story_outline_entry.content,
        )
        self._remember(project_id, "story_outline", story_outline)

        brief = ProjectBrief(
            project_id=project_id,
            prompt=creative_brief["raw_idea"],
            target_duration_sec=prior_plan["target_duration_sec"],
            aspect_ratio=prior_plan["aspect_ratio"],
        )
        director_plan = self._assemble(brief, story_outline)
        self._remember(project_id, "director_plan", director_plan)
        return director_plan

    def _assemble(self, brief: ProjectBrief, story_outline: dict[str, Any]) -> dict[str, Any]:
        scenes = self._scene_generator.generate_scenes(story_outline)
        for scene, skeleton_entry in zip(scenes, story_outline["scene_skeleton"], strict=True):
            scene["shots"] = self._shot_planner.plan_shots(
                scene, skeleton_entry["estimated_duration_sec"]
            )

        anchors = story_outline.get("continuity_anchors", {})
        continuity_notes = ", ".join(anchors.get("characters", []) + anchors.get("locations", []))
        capabilities = self._llm.capabilities()

        director_plan = {
            "schema_version": "1.0",
            "project_id": brief.project_id,
            "logline": story_outline["logline"],
            "target_duration_sec": brief.target_duration_sec,
            "aspect_ratio": brief.aspect_ratio,
            "global_style": {
                "visual_style": story_outline.get("global_style_hint") or "cinematic photorealistic",
            },
            "negative_prompt_global": DEFAULT_NEGATIVE_PROMPT,
            "continuity_notes": continuity_notes,
            "scenes": scenes,
            "generated_by": {
                "provider_id": capabilities.provider_id,
                "model": capabilities.model_id,
                "prompt_template_id": "story_planner",
                "prompt_template_version": "1",
            },
        }

        try:
            schemas.validate(director_plan, "director_plan")
        except jsonschema.ValidationError as exc:
            raise SchemaValidationError(
                f"CreativeDirector assembled an invalid DirectorPlan: {exc.message}"
            ) from exc

        return director_plan

    def _remember(self, project_id: str, stage: str, content: dict[str, Any]) -> None:
        self._memory.append(
            project_id, DirectorMemoryEntry(stage=stage, content=content, created_at=time.time())
        )
