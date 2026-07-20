# libraries/prompt-library

Content, not code: reusable, versioned prompt fragments that
`services/prompt-builder` draws on when composing a shot's
`positive_prompt`/`negative_prompt`. Organized by style so a given
`global_style.visual_style` (see `packages/schemas/json/style.schema.json`)
maps to a curated set of phrasing fragments rather than the LLM
reinventing genre-appropriate vocabulary from scratch every time.

## Format

Each file under `styles/` is a list of fragments:

```yaml
style_id: cinematic
version: "1"
fragments:
  - id: cinematic_lighting_base
    text: "cinematic lighting, shot on 35mm film, shallow depth of field"
    tags: [lighting, lens]
  - id: negative_common_artifacts
    negative: true
    text: "distorted anatomy, extra limbs, flicker, text, watermark, low quality"
    tags: [negative, universal]
```

## Quality feedback loop (Phase 2+)

Each fragment is expected to eventually carry a `quality_score` populated
from downstream signals (user approval rate of storyboards using it,
explicit ratings) so the Prompt Builder can prefer higher-performing
fragments over time. Not implemented in Phase 0 — see `docs/ARCHITECTURE.md` roadmap.
