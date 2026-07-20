from __future__ import annotations

from dataclasses import dataclass

from jinja2 import Template


@dataclass(frozen=True)
class PromptTemplate:
    """A versioned system/user prompt pair for one AI Director pipeline
    stage (Creative Brief Parser, Story Planner, ...). Backed by a YAML
    file in libraries/prompt-templates/<template_id>/v<version>.yaml -
    this class is just the in-memory, renderable form of that file.
    """

    template_id: str
    version: str
    system_template: str
    user_template: str
    output_schema_name: str | None = None

    def render(self, **variables: object) -> tuple[str, str]:
        system_prompt = Template(self.system_template).render(**variables)
        user_prompt = Template(self.user_template).render(**variables)
        return system_prompt, user_prompt
