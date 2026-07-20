# services/creative-brief-parser

## Creative Brief Parser

**Responsibility:** first stage of the Creative Director pipeline. Turns
a user's raw, free-text idea (plus any explicit constraints already on
`ProjectBrief`: target duration, aspect ratio) into a structured
`CreativeBrief` — genre, tone, target audience, key message, explicit
inclusions/exclusions, and any ambiguities the parser had to guess at.

**Input:** raw idea string + optional duration/aspect-ratio hints

**Output:** `creative_brief.schema.json`

**Consumed by:** Story Planner (via `services/ai-director`'s
`CreativeDirector` orchestration)

## Why this is a separate stage from Story Planner

Splitting "understand what the user wants" from "design the narrative
structure" keeps each LLM call focused and each prompt template
independently versionable (see `libraries/prompt-templates/`). It also
means a bad narrative-structure call can be retried/regenerated without
re-parsing the brief, and vice versa.

## Status (Phase 1)

Implemented: builds its prompt via `packages/prompt-engine`, calls
whichever `ILLMProvider` it's given (in production, wrapped in
`RetryingLLMProvider`), and validates the result against
`creative_brief.schema.json` before returning it.
