from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import jsonschema
from referencing import Registry, Resource

_SCHEMA_DIR = Path(__file__).resolve().parent.parent.parent / "json"


@lru_cache(maxsize=None)
def load_schema(name: str) -> dict[str, Any]:
    """Load one of the canonical JSON Schemas by name, e.g. load_schema("director_plan")."""
    return json.loads((_SCHEMA_DIR / f"{name}.schema.json").read_text())


@lru_cache(maxsize=None)
def _registry() -> Registry:
    """Builds a referencing.Registry from every schema file in json/, so
    cross-file $refs (e.g. director_plan -> scene -> shot -> camera/
    lighting/motion/style) resolve correctly. Required because
    jsonschema.validate()'s default registry has no knowledge of sibling
    schema files - each must be explicitly registered by its $id.
    """
    resources = [
        Resource.from_contents(json.loads(path.read_text()))
        for path in _SCHEMA_DIR.glob("*.schema.json")
    ]
    return Registry().with_resources((resource.id(), resource) for resource in resources)


def validate(instance: Any, schema_name: str) -> None:
    """Validate `instance` against the named schema with cross-file $refs
    correctly resolved. Raises jsonschema.ValidationError on failure -
    this is the validation entry point every service should use instead
    of calling jsonschema.validate(instance, load_schema(name)) directly,
    which silently fails to resolve $refs like "style.schema.json"."""
    validator = jsonschema.Draft202012Validator(load_schema(schema_name), registry=_registry())
    validator.validate(instance)


def without_required(schema: dict[str, Any], exclude: set[str]) -> dict[str, Any]:
    """Return a shallow copy of `schema` with the given field names removed
    from its `required` list.

    Several schemas (creative_brief, story_outline, director_plan, ...)
    require fields like `schema_version` and `project_id` that calling
    code injects itself rather than asking the LLM to produce - the LLM
    should never be told those are its responsibility to fill in. Callers
    that pass a schema straight to StructuredGenerationRequest.output_schema
    (which both becomes the tool's input_schema for ClaudeProvider and
    what RetryingLLMProvider validates the raw LLM output against) should
    use this to build that LLM-facing schema, then separately validate
    the fully-assembled object (with the injected fields added back in)
    using validate() against the unmodified schema as a final check.
    """
    relaxed = dict(schema)
    relaxed["required"] = [field for field in schema.get("required", []) if field not in exclude]
    return relaxed
