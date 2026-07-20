# tests

Cross-service integration tests (e.g. "a ProjectBrief flows through
CreativeDirector -> Creative Compiler -> LocalProvider and produces a valid
RawClip stub") live here. Unit tests for a single service/package live
next to it in that package's own `tests/` directory instead.

**Status:** empty in Phase 0 — the first meaningful integration test
becomes possible once `services/ai-director` has a real `ILLMProvider`
implementation (Phase 1) or once the Creative Compiler services exist
(Phase 2), so tests can exercise something beyond `NotImplementedError`
stubs.
