# ADR 0001: Separate the AI Director (LLM) layer from the Video Engine layer

**Status:** Accepted

## Context

The project's stated goal is to compete with Runway/Veo/Kling using an
open-source video engine (starting with Wan2.1) as the execution backend,
while Claude (or any other LLM) acts purely as a creative director. Two
requirements follow directly from this:

1. The LLM must never generate video, frames, or pixels — only a
   structured production plan.
2. Both the LLM provider and the video engine must be replaceable
   independently, without the other side (or anything in between)
   changing.

## Decision

The system has exactly one contract between the two layers:
`DirectorPlan` (see `packages/schemas/json/director_plan.schema.json`),
produced by `AIDirector` (`services/ai-director`) via any
`ILLMProvider` implementation, and consumed only by the Creative Compiler
pipeline (Scene Builder → ... → Render Configuration Compiler). The
Compiler's output, `RenderSpec`
(`packages/schemas/json/render_configuration.schema.json`), is the only
contract handed to `IVideoEngine` implementations.

No service is permitted to:
- Import a specific LLM vendor SDK outside `packages/llm-providers` (or a
  `plugins/llm-providers` entry).
- Import Wan2.1-specific code, or any other engine-specific code, outside
  `services/video-engine-adapter` (or a `plugins/video-engines` entry).
- Pass free-text prompts or engine-specific parameters through any schema
  above `render_configuration.schema.json`.

## Consequences

- Swapping Claude for another LLM means writing one new `ILLMProvider`
  implementation and changing `LLM_PROVIDER` in config. No Planner,
  Compiler, or Orchestrator code changes.
- Swapping Wan2.1 for a custom foundation model means writing one new
  `IVideoEngine` implementation and changing `VIDEO_ENGINE` in config. No
  Planner, Compiler, or Orchestrator code changes — this is the literal
  mechanism behind "today: Claude → Wan2.1, in a year: Claude → my
  foundation model, without rewriting the system."
- Every cross-module payload must be validated against its schema at the
  boundary (see `AIDirector.generate_director_plan`, which validates the
  LLM's output before returning it) — this is a small amount of extra
  code in exchange for the entire system being safe to swap parts out of.
- A Planner that needs an LLM-backed creative sub-decision takes its own
  `ILLMProvider` dependency directly; it does not route back through
  `AIDirector`, keeping that service a single testable entry point for
  the one contract that matters (brief in, `DirectorPlan` out).
