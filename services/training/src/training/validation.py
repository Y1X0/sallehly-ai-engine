from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ValidationIssue:
    """One finding from any Phase 9 validation pass - shared shape
    between `dataset.interfaces.IDatasetValidator` and
    `registry.compatibility`'s checkpoint/`CapabilityManifest`
    compatibility check, so both report findings the same way rather
    than each inventing their own severity/field/message tuple."""

    severity: str
    """"error" (blocks promotion/dataset inclusion) or "warning" (worth
    surfacing, never blocking)."""
    field: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {"severity": self.severity, "field": self.field, "message": self.message}


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    issues: tuple[ValidationIssue, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"valid": self.valid, "issues": [i.to_dict() for i in self.issues]}
