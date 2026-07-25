from __future__ import annotations

from .interfaces import IDatasetValidator, ValidationIssue, ValidationResult
from .records import ClipRecord


class DatasetValidator(IDatasetValidator):
    """Real, deterministic checks against `ClipRecord` - no model, no
    GPU, no network. Thresholds are constructor parameters rather than
    module constants so a golden-benchmark curation pass (Phase 9
    roadmap Stage 2/3) can tighten or loosen them per dataset without
    subclassing."""

    def __init__(
        self,
        *,
        min_duration_sec: float = 0.5,
        max_duration_sec: float = 120.0,
        min_height: int = 480,
        min_fps: float = 12.0,
        require_caption: bool = False,
    ) -> None:
        self._min_duration_sec = min_duration_sec
        self._max_duration_sec = max_duration_sec
        self._min_height = min_height
        self._min_fps = min_fps
        self._require_caption = require_caption

    def validate(self, record: ClipRecord) -> ValidationResult:
        issues: list[ValidationIssue] = []

        if not record.rights_cleared:
            issues.append(
                ValidationIssue(
                    "error",
                    "rights_cleared",
                    "Clip has no documented rights clearance - every clip needs an auditable "
                    "rights chain before it may enter a training dataset version.",
                )
            )

        if record.metadata.duration_sec < self._min_duration_sec:
            issues.append(
                ValidationIssue(
                    "error",
                    "metadata.duration_sec",
                    f"Duration {record.metadata.duration_sec}s is below the {self._min_duration_sec}s floor.",
                )
            )
        if record.metadata.duration_sec > self._max_duration_sec:
            issues.append(
                ValidationIssue(
                    "error",
                    "metadata.duration_sec",
                    f"Duration {record.metadata.duration_sec}s exceeds the {self._max_duration_sec}s ceiling - "
                    "run scene-cut detection to split this into single-shot clips first.",
                )
            )

        if record.metadata.height < self._min_height:
            issues.append(
                ValidationIssue(
                    "error",
                    "metadata.height",
                    f"Height {record.metadata.height}px is below the {self._min_height}px floor.",
                )
            )

        if record.metadata.fps < self._min_fps:
            issues.append(
                ValidationIssue(
                    "error",
                    "metadata.fps",
                    f"Frame rate {record.metadata.fps}fps is below the {self._min_fps}fps floor.",
                )
            )

        if not record.caption:
            severity = "error" if self._require_caption else "warning"
            issues.append(
                ValidationIssue(
                    severity,
                    "caption",
                    "Clip has no caption yet - run the caption pipeline before finalizing a dataset version.",
                )
            )

        valid = not any(issue.severity == "error" for issue in issues)
        return ValidationResult(valid=valid, issues=tuple(issues))
