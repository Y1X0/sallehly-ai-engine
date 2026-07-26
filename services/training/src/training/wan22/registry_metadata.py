from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ..validation import ValidationIssue, ValidationResult
from .lora_config import expected_experts

_KNOWN_WAN22_ENGINE_IDS = frozenset({"wan2.2-ti2v-5b", "wan2.2-t2v-a14b", "wan2.2-i2v-a14b"})


@dataclass(frozen=True)
class Wan22DownloadSpec:
    """The `download:` block of one Wan2.2 engine entry in
    `models/registry.yaml` - everything `training.hf_download` needs to
    fetch that engine's real weights from Hugging Face Hub."""

    source: str
    repo_id: str
    revision: str
    allow_patterns: tuple[str, ...]
    approx_download_size_gb: float

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Wan22DownloadSpec":
        return cls(
            source=data["source"],
            repo_id=data["repo_id"],
            revision=data.get("revision", "main"),
            allow_patterns=tuple(data.get("allow_patterns") or ()),
            approx_download_size_gb=float(data.get("approx_download_size_gb", 0.0)),
        )


@dataclass(frozen=True)
class Wan22RegistryEntry:
    """One Wan2.2 `engine_id` entry from `models/registry.yaml`, parsed
    into a real structure `training.hf_download` and
    `training.wan22.diffusers_backend.default_model_sources` can consume
    - rather than every caller re-parsing the raw YAML dict."""

    engine_id: str
    engine_version: str
    status: str
    license: str
    capability_manifest: str
    experts: dict[str, str]  # expert_name -> subfolder
    download: Wan22DownloadSpec
    lora_adapters_root: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Wan22RegistryEntry":
        return cls(
            engine_id=data["engine_id"],
            engine_version=data["engine_version"],
            status=data.get("status", ""),
            license=data.get("license", ""),
            capability_manifest=data.get("capability_manifest", ""),
            experts={name: spec["subfolder"] for name, spec in (data.get("experts") or {}).items()},
            download=Wan22DownloadSpec.from_dict(data["download"]),
            lora_adapters_root=(data.get("checkpoints") or {}).get("lora_adapters_root", ""),
        )


def load_wan22_registry_entries(registry_path: str | Path = "models/registry.yaml") -> dict[str, Wan22RegistryEntry]:
    """Reads `models/registry.yaml` and returns every `engine_id` that is
    a known Wan2.2 training target, keyed by `engine_id`. Real disk I/O
    and real YAML parsing - no GPU, no network, no model weights
    involved."""
    data = yaml.safe_load(Path(registry_path).read_text())
    entries: dict[str, Wan22RegistryEntry] = {}
    for engine in data.get("engines") or []:
        engine_id = engine.get("engine_id")
        if engine_id in _KNOWN_WAN22_ENGINE_IDS and engine.get("download"):
            entries[engine_id] = Wan22RegistryEntry.from_dict(engine)
    return entries


def validate_wan22_registry_entry(entry: Wan22RegistryEntry) -> ValidationResult:
    """Real, structural checks against one `Wan22RegistryEntry` - the
    Wan2.2 counterpart to `registry.compatibility.validate_capability_manifest`,
    checking the *registry metadata* (which experts exist, where their
    weights come from) rather than the *capability envelope*. Run this
    before `training.hf_download` acts on an entry, and before
    `training.wan22.diffusers_backend.default_model_sources` is used to
    build a `Wan22DiffusersBackend` from it.
    """
    issues: list[ValidationIssue] = []

    if entry.engine_id not in _KNOWN_WAN22_ENGINE_IDS:
        issues.append(
            ValidationIssue(
                "error", "engine_id", f"{entry.engine_id!r} is not a known Wan2.2 engine id "
                f"(expected one of {sorted(_KNOWN_WAN22_ENGINE_IDS)})",
            )
        )
        return ValidationResult(valid=False, issues=tuple(issues))

    try:
        required_experts = expected_experts(entry.engine_id)
    except ValueError as exc:
        issues.append(ValidationIssue("error", "engine_id", str(exc)))
        return ValidationResult(valid=False, issues=tuple(issues))

    actual_experts = frozenset(entry.experts)
    if actual_experts != required_experts:
        issues.append(
            ValidationIssue(
                "error", "experts",
                f"registry entry for {entry.engine_id!r} declares experts {sorted(actual_experts)}, "
                f"but expected_experts() requires exactly {sorted(required_experts)}",
            )
        )
    for expert_name, subfolder in entry.experts.items():
        if not subfolder.strip():
            issues.append(ValidationIssue("error", f"experts.{expert_name}.subfolder", "must not be empty"))

    if entry.download.source != "huggingface":
        issues.append(
            ValidationIssue(
                "error", "download.source",
                f"only 'huggingface' is a supported download source, got {entry.download.source!r}",
            )
        )
    if not entry.download.repo_id.strip():
        issues.append(ValidationIssue("error", "download.repo_id", "must not be empty"))
    if "/" not in entry.download.repo_id:
        issues.append(
            ValidationIssue(
                "error", "download.repo_id",
                f"{entry.download.repo_id!r} does not look like an 'owner/name' HF Hub repo id",
            )
        )
    if not entry.download.allow_patterns:
        issues.append(
            ValidationIssue(
                "warning", "download.allow_patterns",
                "no allow_patterns set - a download would fetch the entire repo",
            )
        )

    if not entry.capability_manifest.strip():
        issues.append(ValidationIssue("error", "capability_manifest", "must not be empty"))
    elif not Path(entry.capability_manifest).is_file():
        issues.append(
            ValidationIssue(
                "error", "capability_manifest", f"file does not exist: {entry.capability_manifest}",
            )
        )

    if not entry.lora_adapters_root.strip():
        issues.append(ValidationIssue("error", "checkpoints.lora_adapters_root", "must not be empty"))

    valid = not any(issue.severity == "error" for issue in issues)
    return ValidationResult(valid=valid, issues=tuple(issues))
