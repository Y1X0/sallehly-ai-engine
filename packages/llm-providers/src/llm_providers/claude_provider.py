from __future__ import annotations

from .base import (
    ILLMProvider,
    LLMCapabilities,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)


class ClaudeProvider(ILLMProvider):
    """Reference ILLMProvider implementation backed by the Claude API.

    This is the default provider (see .env.example: LLM_PROVIDER=claude)
    but is otherwise an ordinary plugin - registered in
    plugins/llm-providers and selected purely by config. Swapping to
    another provider means adding a sibling class here and changing
    LLM_PROVIDER, nothing else.
    """

    provider_id = "claude"

    def __init__(self, api_key: str, model_id: str = "claude-sonnet-5") -> None:
        self._api_key = api_key
        self._model_id = model_id

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
        raise NotImplementedError(
            "Phase 1: wire the Anthropic SDK tool-use call here and validate "
            "the result against request.output_schema before returning."
        )
