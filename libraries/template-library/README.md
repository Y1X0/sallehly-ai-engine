# libraries/template-library

Content, not code: full `DirectorPlan` skeletons for common video genres,
used to seed/guide the AI Director's output for a matching
`style_preset_id` in a `ProjectBrief`. These raise output quality and
consistency from the first request, rather than relying purely on the
LLM inferring genre conventions from a short brief.

## Format

Each file is a partial `DirectorPlan`
(`packages/schemas/json/director_plan.schema.json`) with `scenes[].shots[]`
left as guidance placeholders — the AI Director fills in the specifics
of a given brief but inherits the template's scene count, pacing, and
`global_style` as a starting point.

See `product-ad.yaml` for a worked example.
