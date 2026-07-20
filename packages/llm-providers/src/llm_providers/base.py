from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LLMCapabilities:
    provider_id: str
    model_id: str
    supports_structured_output: bool
    supports_vision: bool
    max_context_tokens: int


@dataclass(frozen=True)
class StructuredGenerationRequest:
    system_prompt: str
    user_prompt: str
    output_schema: dict[str, Any]
    reference_image_uris: list[str] | None = None
    temperature: float = 0.7


@dataclass(frozen=True)
class StructuredGenerationResult:
    output: dict[str, Any]
    provider_id: str
    model_id: str
    raw_usage: dict[str, Any] | None = None


class ILLMProvider(ABC):
    """The only contract the AI Director is allowed to depend on.

    Every module above this line (ai-director, prompt-builder, and every
    Planner that needs a creative sub-decision from an LLM) talks to
    whichever provider is configured purely through this interface. No
    module outside this package may import a vendor SDK (anthropic,
    openai, ...) directly - see docs/adr/0001-director-engine-separation.md.
    """

    @abstractmethod
    def capabilities(self) -> LLMCapabilities: ...

    @abstractmethod
    def generate_structured(
        self, request: StructuredGenerationRequest
    ) -> StructuredGenerationResult:
        """Generate output that MUST validate against request.output_schema.

        Implementations should use the provider's native structured
        output / tool-calling mechanism where available, and raise
        SchemaValidationError (see errors.py) if the provider cannot be
        made to conform.
        """
        ...
