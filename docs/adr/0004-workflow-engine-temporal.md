# ADR 0004: Temporal.io for render orchestration, isolated behind one service

**Status:** Accepted (per explicit decision from the project owner: adopt
Temporal now, keep it replaceable later)

## Context

A single render job is a long-running, multi-step process (submit to
compute provider → poll → fetch → post-process → export) that must
survive process restarts, retry transient GPU failures, and pause for a
human approval signal at the storyboard stage. This is exactly the
problem durable workflow engines solve; Temporal is the most mature
open-source option with first-class support for signals (used for the
storyboard approval gate) and automatic retry policies.

## Decision

Adopt Temporal now. All Temporal-specific code (workflow and activity
definitions) lives inside `services/render-orchestrator/src/render_orchestrator/workflows/`
and nowhere else. No other service imports the Temporal SDK. The
workflow's activities call out to `IVideoEngine`/`IComputeProvider`
exactly as any other caller would — Temporal has no special knowledge of
Wan2.1 or any compute provider.

Local dev runs Temporal via `temporalio/admin-tools`'s `start-dev` server
(`docker-compose.yml`, `temporal` profile) rather than requiring a full
Temporal Cluster.

## Consequences

- Storyboard approval, retries, and long GPU job polling are handled by
  Temporal's primitives (signals, activity retry policies) instead of
  hand-rolled polling loops and a bespoke state machine in Postgres.
- If Temporal ever needs to be replaced (cost, operational complexity, a
  simpler in-house queue proving sufficient), the blast radius is
  `services/render-orchestrator` only — every other service already
  only knows "submit a render, get notified when it's done," not
  "Temporal did this."
- Phase 4 is where this actually gets implemented; Phase 0 only reserves
  the directory and this decision record.
