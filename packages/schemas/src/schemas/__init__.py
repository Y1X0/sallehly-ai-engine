from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_SCHEMA_DIR = Path(__file__).resolve().parent.parent.parent / "json"


@lru_cache(maxsize=None)
def load_schema(name: str) -> dict[str, Any]:
    """Load one of the canonical JSON Schemas by name, e.g. load_schema("director_plan")."""
    return json.loads((_SCHEMA_DIR / f"{name}.schema.json").read_text())
