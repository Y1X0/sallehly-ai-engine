from __future__ import annotations

from typing import Any

from .base import ILLMProvider, LLMCapabilities, StructuredGenerationRequest, StructuredGenerationResult


class FakeLLMProvider(ILLMProvider):
    """Test double: returns a pre-scripted sequence of outputs, one per
    call, in order. Used by tests/test_creative_pipeline.py to exercise
    the whole Creative Director pipeline without a real API key.

    Not a mock of Claude's behavior (it does not validate its own output
    or simulate tool-use) - it exists purely to let callers of
    ILLMProvider be tested in isolation from any real vendor.
    """

    provider_id = "fake"

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = list(responses)
        self._call_count = 0
        self.received_requests: list[StructuredGenerationRequest] = []

    def capabilities(self) -> LLMCapabilities:
        return LLMCapabilities(
            provider_id=self.provider_id,
            model_id="fake-1",
            supports_structured_output=True,
            supports_vision=False,
            max_context_tokens=100_000,
        )

    def generate_structured(
        self, request: StructuredGenerationRequest
    ) -> StructuredGenerationResult:
        self.received_requests.append(request)
        if self._call_count >= len(self._responses):
            raise IndexError(
                f"FakeLLMProvider received more calls ({self._call_count + 1}) "
                f"than scripted responses ({len(self._responses)})"
            )
        output = self._responses[self._call_count]
        self._call_count += 1
        return StructuredGenerationResult(output=output, provider_id=self.provider_id, model_id="fake-1")
