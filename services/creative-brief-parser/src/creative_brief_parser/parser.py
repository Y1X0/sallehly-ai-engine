from __future__ import annotations

from typing import Any

import jsonschema
import schemas
from llm_providers import ILLMProvider, StructuredGenerationRequest
from llm_providers.errors import SchemaValidationError
from prompt_engine import PromptTemplateStore
from schemas import without_required

# project_id/raw_idea/schema_version are injected by parse() after the
# call, never asked of the LLM - see schemas.without_required.
_LLM_INJECTED_FIELDS = {"schema_version", "project_id", "raw_idea"}


class CreativeBriefParser:
    """First stage of the Creative Director pipeline: turns a raw user
    idea into a structured CreativeBrief (packages/schemas/json/creative_brief.schema.json).

    Takes its own ILLMProvider dependency directly rather than routing
    through services/ai-director, per ADR 0001 - CreativeDirector composes
    this service, it does not replace it.
    """

    def __init__(
        self,
        llm_provider: ILLMProvider,
        template_store: PromptTemplateStore | None = None,
    ) -> None:
        self._llm = llm_provider
        self._templates = template_store or PromptTemplateStore()
        self._llm_schema = without_required(schemas.load_schema("creative_brief"), _LLM_INJECTED_FIELDS)

    def parse(
        self,
        project_id: str,
        raw_idea: str,
        *,
        target_duration_sec: float | None = None,
        aspect_ratio: str | None = None,
    ) -> dict[str, Any]:
        template = self._templates.load("creative_brief_parser")
        system_prompt, user_prompt = template.render(
            raw_idea=raw_idea,
            target_duration_sec=target_duration_sec,
            aspect_ratio=aspect_ratio,
        )
        request = StructuredGenerationRequest(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            output_schema=self._llm_schema,
        )
        result = self._llm.generate_structured(request)

        brief = dict(result.output)
        brief.setdefault("schema_version", "1.0")
        brief["project_id"] = project_id
        brief["raw_idea"] = raw_idea  # authoritative input, not left to the LLM to transcribe

        try:
            schemas.validate(brief, "creative_brief")
        except jsonschema.ValidationError as exc:
            raise SchemaValidationError(
                f"CreativeBriefParser produced an invalid CreativeBrief: {exc.message}"
            ) from exc

        return brief
