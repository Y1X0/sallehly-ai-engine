from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from .template import PromptTemplate

_DEFAULT_TEMPLATES_DIR = Path(__file__).resolve().parents[4] / "libraries" / "prompt-templates"


class PromptTemplateNotFoundError(Exception):
    pass


class PromptTemplateStore:
    """Loads versioned prompt templates from libraries/prompt-templates/.

    Every AI Director pipeline stage that calls an LLM loads its prompt
    through this store rather than hardcoding prompt text in Python, so
    prompt iteration never requires a code change or redeploy of the
    service using it - only a new version file (see README.md in
    libraries/prompt-templates for the versioning convention).
    """

    def __init__(self, templates_dir: Path | None = None) -> None:
        self._templates_dir = templates_dir or _DEFAULT_TEMPLATES_DIR

    def load(self, template_id: str, version: str = "1") -> PromptTemplate:
        return self._load_cached(self._templates_dir, template_id, version)

    @staticmethod
    @lru_cache(maxsize=None)
    def _load_cached(templates_dir: Path, template_id: str, version: str) -> PromptTemplate:
        path = templates_dir / template_id / f"v{version}.yaml"
        if not path.exists():
            raise PromptTemplateNotFoundError(f"No template at {path}")
        data = yaml.safe_load(path.read_text())
        return PromptTemplate(
            template_id=data["template_id"],
            version=str(data["version"]),
            system_template=data["system_template"],
            user_template=data["user_template"],
            output_schema_name=data.get("output_schema"),
        )
