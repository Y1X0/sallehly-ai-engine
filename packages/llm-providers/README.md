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
(typically `packages/schemas/json/director_plan.schema.json`, but any
Planner may also use this interface for smaller creative sub-decisions).

## Implementations

| Provider | File | Status |
|---|---|---|
| Claude (Anthropic) | `claude_provider.py` | Phase 1 target, stubbed now |
| OpenAI | *(not started)* | Add as `openai_provider.py` when needed |
| Local / self-hosted LLM | *(not started)* | Add as `local_llm_provider.py` when needed |

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
