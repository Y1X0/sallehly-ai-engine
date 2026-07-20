# packages/director-memory

Per-project history of every artifact the Creative Director's pipeline
produces: `CreativeBrief`, `StoryOutline`, `DirectorPlan`, and reviewer
feedback. This is what makes the storyboard revision loop
(`changes_requested` in `docs/workflows/ai-director-workflow.md`) work:
`CreativeDirector.regenerate_with_feedback` pulls the last `CreativeBrief`
and `StoryOutline` out of memory and re-invokes the Story Planner with
the human's feedback attached, instead of starting over from the raw
idea.

## Interface

```
IDirectorMemoryStore.append(project_id, DirectorMemoryEntry)
IDirectorMemoryStore.history(project_id, stage=None) -> list[DirectorMemoryEntry]
IDirectorMemoryStore.latest(project_id, stage) -> DirectorMemoryEntry | None
```

`stage` is one of `"creative_brief"`, `"story_outline"`, `"director_plan"`,
`"feedback"`.

## Implementations

| Implementation | Status |
|---|---|
| `InMemoryDirectorMemoryStore` | Implemented — process-local dict, used in local dev and tests |
| A Postgres-backed store | Not started — Phase 2+, once the API/DB layer exists. Swapping it in means implementing `IDirectorMemoryStore` again; `CreativeDirector` does not change. |

## Non-goals (for now)

This is not a semantic/vector memory. It answers "what did we already
decide for project X," not "find me projects similar to this one." A
similarity-search layer (backed by the Vector DB mentioned in
`docs/ARCHITECTURE.md`) is a separate, later concern if the product needs
it (e.g. "reuse a prompt fragment that worked well for a similar brief").
