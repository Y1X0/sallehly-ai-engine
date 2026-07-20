# ADR 0006: Structured output enforcement as a provider-agnostic retry decorator

**Status:** Accepted

## Context

Every LLM-backed stage (Creative Brief Parser, Story Planner, and any
future stage) needs its output to reliably conform to a JSON Schema.
Claude's tool-use with a forced `tool_choice` gets close, but is not an
absolute guarantee across all inputs, and a second provider added later
(per ADR 0001) may have weaker structured-output guarantees. Retry logic
implemented separately inside each provider, or inside each caller,
would be duplicated and inconsistent.

## Decision

`ClaudeProvider.generate_structured` forces structured output via a
single tool whose `input_schema` is the caller's requested schema and a
pinned `tool_choice` (see `packages/llm-providers/src/llm_providers/claude_provider.py`).

On top of that, `RetryingLLMProvider` (`packages/llm-providers/src/llm_providers/retry.py`)
wraps *any* `ILLMProvider` and adds a second, provider-agnostic layer:
validate the output against `request.output_schema` with `jsonschema`;
on failure, append the invalid output and the validation error to the
user prompt and retry (default: 2 retries); raise `SchemaValidationError`
if still invalid after all retries.

`CreativeDirector` always constructs its `ILLMProvider` dependency
wrapped in `RetryingLLMProvider` — every LLM-backed stage it composes
(`CreativeBriefParser`, `StoryPlanner`) gets this for free without
implementing it themselves.

## Consequences

- Adding a second LLM provider (e.g. `OpenAIProvider`) requires zero
  retry/validation code in that provider — it gets `RetryingLLMProvider`
  automatically, same as `ClaudeProvider`.
- The retry prompt includes the actual validation error message, which
  in practice gets a model closer to a fix on the next attempt than a
  generic "try again" would.
- A test double (`FakeLLMProvider`, `packages/llm-providers/src/llm_providers/testing.py`)
  can be wrapped in `RetryingLLMProvider` exactly like a real provider,
  which is how `tests/test_creative_pipeline.py` exercises the retry path
  without a live API key.
- Cost note: each retry is a full additional LLM call. `max_retries=2` is
  a starting default; if real-world validation failure rates turn out
  high enough to matter for cost, tightening the prompt/schema (fewer
  free-text fields, more enums) is a cheaper fix than raising the retry
  budget.
