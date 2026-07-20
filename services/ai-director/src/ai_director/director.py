from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import jsonschema
from llm_providers import ILLMProvider, StructuredGenerationRequest
from llm_providers.errors import SchemaValidationError
from schemas import load_schema

from .prompts import DIRECTOR_SYSTEM_PROMPT


@dataclass(frozen=True)
class ProjectBrief:
    """Mirrors the `brief` object in packages/schemas/json/project.schema.json."""

    project_id: str
    prompt: str
    target_duration_sec: float
    aspect_ratio: str
    reference_asset_ids: list[str] | None = None
    style_preset_id: str | None = None


class AIDirector:
    """The only place in the system that talks to an ILLMProvider to
    produce a DirectorPlan. Everything downstream (Prompt Builder, Scene
    Builder, ...) consumes the plan this returns and never touches the
    LLM directly.
    """

    def __init__(self, llm_provider: ILLMProvider) -> None:
        self._llm_provider = llm_provider
        self._director_plan_schema = load_schema("director_plan")

    def generate_director_plan(self, brief: ProjectBrief) -> dict[str, Any]:
        request = StructuredGenerationRequest(
            system_prompt=DIRECTOR_SYSTEM_PROMPT,
            user_prompt=self._render_user_prompt(brief),
            output_schema=self._director_plan_schema,
        )
        result = self._llm_provider.generate_structured(request)

        try:
            jsonschema.validate(result.output, self._director_plan_schema)
        except jsonschema.ValidationError as exc:
            raise SchemaValidationError(
                f"{result.provider_id}/{result.model_id} produced a DirectorPlan "
                f"that failed schema validation: {exc.message}"
            ) from exc

        return result.output

    @staticmethod
    def _render_user_prompt(brief: ProjectBrief) -> str:
        lines = [
            f"Project id: {brief.project_id}",
            f"Client brief: {brief.prompt}",
            f"Target duration: {brief.target_duration_sec} seconds",
            f"Aspect ratio: {brief.aspect_ratio}",
        ]
        if brief.style_preset_id:
            lines.append(f"Requested style preset: {brief.style_preset_id}")
        if brief.reference_asset_ids:
            lines.append(f"Reference assets: {', '.join(brief.reference_asset_ids)}")
        return "\n".join(lines)
