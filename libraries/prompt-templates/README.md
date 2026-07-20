# libraries/prompt-templates

Versioned system/user prompt pairs for the AI Director's LLM-backed
pipeline stages. Loaded and rendered via `packages/prompt-engine`.

**Not the same thing as `libraries/prompt-library`** (video-generation
prompt fragments for `services/prompt-builder`) or
`libraries/template-library` (full `DirectorPlan` genre templates). This
directory is one level up the stack: the prompts that ask an LLM to
*produce* a `CreativeBrief` or a `StoryOutline` in the first place.

## Layout

```
<template_id>/
  v1.yaml
  v2.yaml   (added when the prompt changes meaningfully; v1 kept until unused)
```

## Current templates

| `template_id` | Used by | Produces |
|---|---|---|
| `creative_brief_parser` | `services/creative-brief-parser` | `creative_brief.schema.json` |
| `story_planner` | `services/story-planner` | `story_outline.schema.json` |
