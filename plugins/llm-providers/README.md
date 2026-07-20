# plugins/llm-providers

Third-party or optional `ILLMProvider` implementations that shouldn't
live in the core `packages/llm-providers` package (e.g. community
contributions, or providers only some deployments use).

The reference implementation (`ClaudeProvider`) lives in
`packages/llm-providers` itself since it's the default. Anything added
here registers under a unique `provider_id` the same way — see
`packages/config-sdk` for the registry mechanism.

**Status:** empty by design in Phase 0. Nothing to add until a second
provider is needed.
