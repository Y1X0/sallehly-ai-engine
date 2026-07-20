class LLMProviderError(Exception):
    """Base class for all llm-providers errors."""


class SchemaValidationError(LLMProviderError):
    """Raised when a provider's output cannot be made to validate against
    the requested output_schema after all provider-side retries."""


class ProviderUnavailableError(LLMProviderError):
    """Raised on transport/auth failure talking to the underlying provider."""
