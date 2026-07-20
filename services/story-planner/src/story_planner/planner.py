from __future__ import annotations

from typing import Any

import jsonschema
import schemas
from llm_providers import ILLMProvider, StructuredGenerationRequest
from llm_providers.errors import SchemaValidationError
from prompt_engine import PromptTemplateStore
from schemas import without_required

# project_id/schema_version are injected by plan() after the call, never
# asked of the LLM - see schemas.without_required.
_LLM_INJECTED_FIELDS = {"schema_version", "project_id"}


class StoryPlanner:
    """Second stage of the Creative Director pipeline: turns a
    CreativeBrief into a StoryOutline (narrative arc + scene skeleton),
    without deciding shots, camera, lighting, motion, or style.

    Also handles the revision path: when a storyboard is rejected with
    feedback, `plan(..., feedback=..., prior_story_outline=...)` asks for
    a targeted revision instead of a from-scratch outline.
    """

    def __init__(
        self,
        llm_provider: ILLMProvider,
        template_store: PromptTemplateStore | None = None,
    ) -> None:
        self._llm = llm_provider
        self._templates = template_store or PromptTemplateStore()
        self._llm_schema = without_required(schemas.load_schema("story_outline"), _LLM_INJECTED_FIELDS)

    def plan(
        self,
        creative_brief: dict[str, Any],
        *,
        target_duration_sec: float,
        aspect_ratio: str,
        feedback: list[str] | None = None,
        prior_story_outline: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        template = self._templates.load("story_planner")
        system_prompt, user_prompt = template.render(
            creative_brief=creative_brief,
            target_duration_sec=target_duration_sec,
            aspect_ratio=aspect_ratio,
            feedback=feedback,
            prior_story_outline=prior_story_outline,
        )
        request = StructuredGenerationRequest(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            output_schema=self._llm_schema,
        )
        result = self._llm.generate_structured(request)

        outline = dict(result.output)
        outline.setdefault("schema_version", "1.0")
        outline["project_id"] = creative_brief["project_id"]

        try:
            schemas.validate(outline, "story_outline")
        except jsonschema.ValidationError as exc:
            raise SchemaValidationError(
                f"StoryPlanner produced an invalid StoryOutline: {exc.message}"
            ) from exc

        return outline
