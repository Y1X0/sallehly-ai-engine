from __future__ import annotations

from video_engine_sdk import CapabilityManifest

from ..validation import ValidationIssue, ValidationResult

_KNOWN_MODES = frozenset({"text_to_video", "image_to_video", "video_edit"})


def validate_capability_manifest(manifest: CapabilityManifest) -> ValidationResult:
    """Real, structural checks against `IVideoEngine`'s actual contract
    shape (`packages/video-engine-sdk`) - the same fields
    `RenderConfigCompiler`/`GenerationPipeline` genuinely read, not a
    guess at what might matter. Run before a `ModelVersionRecord` is
    allowed to promote past `PromotionStatus.STAGING`
    (`registry.filesystem_registry.FilesystemModelRegistry.promote`),
    catching the class of mistake this repo already found once for real:
    ADR 0014's SallehlyModelAdapter shipping a placeholder
    `CapabilityManifest` that was never checked against what
    `IVideoEngine` callers actually require."""
    issues: list[ValidationIssue] = []

    if not manifest.engine_id:
        issues.append(ValidationIssue("error", "engine_id", "must not be empty"))

    if not manifest.modes:
        issues.append(ValidationIssue("error", "modes", "must declare at least one supported mode"))
    unknown_modes = set(manifest.modes) - _KNOWN_MODES
    if unknown_modes:
        issues.append(
            ValidationIssue(
                "error",
                "modes",
                f"unknown mode(s) {sorted(unknown_modes)} - RenderSpec.mode only ever takes one of "
                f"{sorted(_KNOWN_MODES)}",
            )
        )

    if manifest.min_shot_duration_sec <= 0:
        issues.append(ValidationIssue("error", "min_shot_duration_sec", "must be positive"))
    if manifest.max_shot_duration_sec < manifest.min_shot_duration_sec:
        issues.append(
            ValidationIssue(
                "error",
                "max_shot_duration_sec",
                f"{manifest.max_shot_duration_sec} is less than min_shot_duration_sec "
                f"{manifest.min_shot_duration_sec}",
            )
        )

    if not manifest.resolutions:
        issues.append(ValidationIssue("error", "resolutions", "must declare at least one resolution"))
    for resolution in manifest.resolutions:
        parts = resolution.lower().split("x", 1)
        if len(parts) != 2 or not all(p.isdigit() for p in parts):
            issues.append(ValidationIssue("error", "resolutions", f"{resolution!r} is not 'WIDTHxHEIGHT'"))

    if not manifest.fps_options:
        issues.append(ValidationIssue("error", "fps_options", "must declare at least one value"))
    elif any(fps <= 0 for fps in manifest.fps_options):
        issues.append(ValidationIssue("error", "fps_options", "all values must be positive"))

    low, high = manifest.motion_strength_range
    if low > high:
        issues.append(ValidationIssue("error", "motion_strength_range", f"min {low} is greater than max {high}"))

    if manifest.min_vram_gb is not None and manifest.min_vram_gb <= 0:
        issues.append(ValidationIssue("error", "min_vram_gb", "must be positive when set"))

    if not manifest.license:
        issues.append(
            ValidationIssue(
                "warning",
                "license",
                "no license recorded - verify and set one before promoting past staging",
            )
        )

    valid = not any(issue.severity == "error" for issue in issues)
    return ValidationResult(valid=valid, issues=tuple(issues))
