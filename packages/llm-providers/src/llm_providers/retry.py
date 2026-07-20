from __future__ import annotations

import dataclasses

import jsonschema

from .base import ILLMProvider, LLMCapabilities, StructuredGenerationRequest, StructuredGenerationResult
from .errors import SchemaValidationError


class RetryingLLMProvider(ILLMProvider):
    """Wraps any ILLMProvider with schema validation + retry-with-feedback.

    This is the "validation and retry mechanism" every AI Director
    pipeline stage relies on: it is a decorator, not a per-provider
    feature, so it applies identically to ClaudeProvider, a future
    OpenAIProvider, or a local/test provider - none of them need to
    implement retry logic themselves.

    On a validation failure, the offending output and the jsonschema
    error message are appended to the user prompt and the request is
    retried, so the model gets concrete feedback about what to fix rather
    than being asked to blindly try again.
    """

    def __init__(self, wrapped: ILLMProvider, max_retries: int = 2) -> None:
        self._wrapped = wrapped
        self._max_retries = max_retries

    def capabilities(self) -> LLMCapabilities:
        return self._wrapped.capabilities()

    def generate_structured(
        self, request: StructuredGenerationRequest
    ) -> StructuredGenerationResult:
        current_request = request
        last_error: jsonschema.ValidationError | None = None

        for attempt in range(self._max_retries + 1):
            result = self._wrapped.generate_structured(current_request)
            try:
                jsonschema.validate(result.output, request.output_schema)
                return result
            except jsonschema.ValidationError as exc:
                last_error = exc
                current_request = dataclasses.replace(
                    current_request,
                    user_prompt=(
                        f"{current_request.user_prompt}\n\n"
                        f"Your previous response was:\n{result.output}\n\n"
                        f"That response failed schema validation: {exc.message}\n"
                        "Return a corrected JSON object that fixes this and still "
                        "conforms to the schema."
                    ),
                )

        raise SchemaValidationError(
            f"{self._wrapped.__class__.__name__} failed schema validation after "
            f"{self._max_retries} retries. Last error: {last_error.message if last_error else 'unknown'}"
        )
