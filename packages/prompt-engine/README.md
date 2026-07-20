# packages/prompt-engine

Loads and renders the versioned system/user prompt pairs used by every
LLM-backed AI Director pipeline stage (Creative Brief Parser, Story
Planner, and any future stage that needs one).

**Not to be confused with `libraries/prompt-library`** — that package
holds reusable *video-generation* prompt fragments consumed by
`services/prompt-builder` when composing a shot's `positive_prompt` for
the Video Engine. This package's templates are director-facing: the
system/user prompts that ask an LLM to produce a `CreativeBrief` or
`StoryOutline`.

## Usage

```python
from prompt_engine import PromptTemplateStore

store = PromptTemplateStore()
template = store.load("creative_brief_parser")  # loads v1 by default
system_prompt, user_prompt = template.render(raw_idea="...", target_duration_sec=20)
```

## Versioning convention

Templates live in `libraries/prompt-templates/<template_id>/v<N>.yaml`.
Bumping a template's prompt wording is a new `vN` file, never an edit to
an existing one — this keeps `DirectorPlan.generated_by.prompt_template_version`
meaningful for audit/A-B comparison. Old versions are only deleted once
nothing references them anymore.

## Template file format

```yaml
template_id: creative_brief_parser
version: "1"
output_schema: creative_brief   # name passed to schemas.load_schema()
system_template: |
  Jinja2 template string...
user_template: |
  Jinja2 template string, rendered with the same **variables kwargs...
```
