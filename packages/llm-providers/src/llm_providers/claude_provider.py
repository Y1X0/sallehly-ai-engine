from __future__ import annotations

from typing import Any

from .base import (
    ILLMProvider,
    LLMCapabilities,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)
from .errors import ProviderUnavailableError

_TOOL_NAME = "emit_structured_output"


class ClaudeProvider(ILLMProvider):
    """Reference ILLMProvider implementation backed by the Claude API.

    Forces structured output via tool-use: a single tool is defined whose
    input_schema is exactly the caller's requested output_schema, and
    tool_choice pins the model to call it, so the response is always a
    tool_use block whose `input` already conforms to the schema (subject
    to RetryingLLMProvider's validation as a second line of defense).

    This is the default provider (LLM_PROVIDER=claude) but is otherwise an
    ordinary plugin - see packages/llm-providers/README.md for how to add
    a sibling.
    """

    provider_id = "claude"

    def __init__(self, api_key: str, model_id: str = "claude-sonnet-5", max_tokens: int = 8192) -> None:
        self._api_key = api_key
        self._model_id = model_id
        self._max_tokens = max_tokens

    def capabilities(self) -> LLMCapabilities:
        return LLMCapabilities(
            provider_id=self.provider_id,
            model_id=self._model_id,
            supports_structured_output=True,
            supports_vision=True,
            max_context_tokens=200_000,
        )

    def generate_structured(
        self, request: StructuredGenerationRequest
    ) -> StructuredGenerationResult:
        try:
            import anthropic
        except ImportError as exc:
            raise ProviderUnavailableError(
                "The 'anthropic' package is required to use ClaudeProvider. "
                "Install it with: uv add anthropic"
            ) from exc

        client = anthropic.Anthropic(api_key=self._api_key)

        try:
            response = client.messages.create(
                model=self._model_id,
                max_tokens=self._max_tokens,
                system=request.system_prompt,
                messages=[{"role": "user", "content": self._build_user_content(request)}],
                tools=[
                    {
                        "name": _TOOL_NAME,
                        "description": "Return the structured result conforming to the required schema.",
                        "input_schema": request.output_schema,
                    }
                ],
                tool_choice={"type": "tool", "name": _TOOL_NAME},
                temperature=request.temperature,
            )
        except anthropic.APIError as exc:
            raise ProviderUnavailableError(f"Claude API call failed: {exc}") from exc

        tool_use_block = next(
            (block for block in response.content if block.type == "tool_use"), None
        )
        if tool_use_block is None:
            raise ProviderUnavailableError(
                "Claude did not return a tool_use block despite a forced tool_choice."
            )

        return StructuredGenerationResult(
            output=tool_use_block.input,
            provider_id=self.provider_id,
            model_id=self._model_id,
            raw_usage=response.usage.model_dump() if response.usage else None,
        )

    @staticmethod
    def _build_user_content(request: StructuredGenerationRequest) -> list[dict[str, Any]] | str:
        if not request.reference_image_uris:
            return request.user_prompt

        content: list[dict[str, Any]] = [
            {"type": "image", "source": {"type": "url", "url": uri}}
            for uri in request.reference_image_uris
        ]
        content.append({"type": "text", "text": request.user_prompt})
        return content
