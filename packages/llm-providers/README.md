# packages/llm-providers

Defines `ILLMProvider` — the single interface every LLM vendor must be
wrapped behind. This is what makes the "Director" layer independent of
Claude specifically.

## Contract

```
ILLMProvider.capabilities() -> LLMCapabilities
ILLMProvider.generate_structured(request: StructuredGenerationRequest) -> StructuredGenerationResult
```

`generate_structured` is the only method the rest of the system calls.
The output is always validated against a caller-supplied JSON Schema
(typically `packages/schemas/json/creative_brief.schema.json` or
`story_outline.schema.json`, but any Planner may also use this interface
for smaller creative sub-decisions).

## Validation and retry

`RetryingLLMProvider` (`retry.py`) wraps any `ILLMProvider` and adds
schema validation + retry-with-feedback: if the wrapped provider's output
fails `jsonschema.validate`, the validation error is appended to the user
prompt and the call is retried (default: 2 retries) before raising
`SchemaValidationError`. This is a decorator, not a per-provider feature —
`services/ai-director`'s `CreativeDirector` always wraps whichever raw
provider it's given:

```python
from llm_providers import RetryingLLMProvider
llm = RetryingLLMProvider(ClaudeProvider(api_key=...), max_retries=2)
```

## Implementations

| Provider | File | Status |
|---|---|---|
| Claude (Anthropic) | `claude_provider.py` | Implemented — forced tool-use structured output via the `anthropic` SDK |
| OpenAI | *(not started)* | Add as `openai_provider.py` when needed |
| Local / self-hosted LLM | *(not started)* | Add as `local_llm_provider.py` when needed |
| Test double | `testing.py`: `FakeLLMProvider` | Implemented — scripted responses, used by `tests/test_creative_pipeline.py` |

## Adding a new provider

1. Implement `ILLMProvider` in a new module here (or in
   `plugins/llm-providers/` if it's a third-party/optional integration).
2. Register it in the provider registry (config-sdk) under a unique
   `provider_id`.
3. Set `LLM_PROVIDER=<provider_id>` in config. No other service changes.

## Non-goals

This package does not know what a "video" is. It has zero knowledge of
Wan2.1, RenderSpec, or any video-engine concept — that separation is the
whole point (see `docs/adr/0001-director-engine-separation.md`).
