"""Tests for services/training/src/training/wan22/registry_metadata.py -
real parsing and structural validation of the Wan2.2 engine entries in
models/registry.yaml. Pure YAML/dataclass logic; no GPU, no network, no
model weights involved.
"""

from __future__ import annotations

from pathlib import Path

from training import load_wan22_registry_entries, validate_wan22_registry_entry
from training.wan22.registry_metadata import Wan22DownloadSpec, Wan22RegistryEntry

_REGISTRY_PATH = Path(__file__).resolve().parents[1] / "models" / "registry.yaml"


class TestLoadWan22RegistryEntries:
    def test_loads_both_real_wan22_engines(self):
        entries = load_wan22_registry_entries(_REGISTRY_PATH)

        assert set(entries) == {"wan2.2-ti2v-5b", "wan2.2-t2v-a14b"}

    def test_ti2v_5b_has_single_unified_expert(self):
        entries = load_wan22_registry_entries(_REGISTRY_PATH)
        entry = entries["wan2.2-ti2v-5b"]

        assert entry.experts == {"unified": "transformer"}
        assert entry.download.repo_id == "Wan-AI/Wan2.2-TI2V-5B-Diffusers"

    def test_t2v_a14b_has_two_moe_experts(self):
        entries = load_wan22_registry_entries(_REGISTRY_PATH)
        entry = entries["wan2.2-t2v-a14b"]

        assert entry.experts == {"high_noise": "transformer", "low_noise": "transformer_2"}
        assert entry.download.repo_id == "Wan-AI/Wan2.2-T2V-A14B-Diffusers"

    def test_wan21_engine_is_not_included_no_download_block(self):
        entries = load_wan22_registry_entries(_REGISTRY_PATH)

        assert "wan2.1" not in entries


class TestValidateWan22RegistryEntry:
    def test_real_registry_entries_are_valid(self):
        entries = load_wan22_registry_entries(_REGISTRY_PATH)
        for engine_id, entry in entries.items():
            result = validate_wan22_registry_entry(entry)
            assert result.valid, (engine_id, result.issues)

    def test_unknown_engine_id_fails(self):
        entry = Wan22RegistryEntry(
            engine_id="wan2.2-nonexistent", engine_version="2.2.0", status="training-target", license="Apache-2.0",
            capability_manifest="models/wan2.2-ti2v-5b/capability_manifest.yaml", experts={"unified": "transformer"},
            download=Wan22DownloadSpec(source="huggingface", repo_id="a/b", revision="main", allow_patterns=("x",), approx_download_size_gb=1.0),
            lora_adapters_root=".training-runs/x/checkpoints",
        )

        result = validate_wan22_registry_entry(entry)

        assert not result.valid
        assert any(issue.field == "engine_id" for issue in result.issues)

    def test_wrong_expert_set_fails(self):
        entry = Wan22RegistryEntry(
            engine_id="wan2.2-ti2v-5b", engine_version="2.2.0", status="training-target", license="Apache-2.0",
            capability_manifest="models/wan2.2-ti2v-5b/capability_manifest.yaml",
            experts={"high_noise": "transformer", "low_noise": "transformer_2"},  # wrong - ti2v-5b is unified
            download=Wan22DownloadSpec(source="huggingface", repo_id="Wan-AI/x", revision="main", allow_patterns=("x",), approx_download_size_gb=1.0),
            lora_adapters_root=".training-runs/x/checkpoints",
        )

        result = validate_wan22_registry_entry(entry)

        assert not result.valid
        assert any(issue.field == "experts" for issue in result.issues)

    def test_non_huggingface_download_source_fails(self):
        entry = Wan22RegistryEntry(
            engine_id="wan2.2-ti2v-5b", engine_version="2.2.0", status="training-target", license="Apache-2.0",
            capability_manifest="models/wan2.2-ti2v-5b/capability_manifest.yaml", experts={"unified": "transformer"},
            download=Wan22DownloadSpec(source="s3", repo_id="a/b", revision="main", allow_patterns=("x",), approx_download_size_gb=1.0),
            lora_adapters_root=".training-runs/x/checkpoints",
        )

        result = validate_wan22_registry_entry(entry)

        assert not result.valid
        assert any(issue.field == "download.source" for issue in result.issues)

    def test_missing_lora_adapters_root_fails(self):
        entry = Wan22RegistryEntry(
            engine_id="wan2.2-ti2v-5b", engine_version="2.2.0", status="training-target", license="Apache-2.0",
            capability_manifest="models/wan2.2-ti2v-5b/capability_manifest.yaml", experts={"unified": "transformer"},
            download=Wan22DownloadSpec(source="huggingface", repo_id="Wan-AI/x", revision="main", allow_patterns=("x",), approx_download_size_gb=1.0),
            lora_adapters_root="",
        )

        result = validate_wan22_registry_entry(entry)

        assert not result.valid
        assert any(issue.field == "checkpoints.lora_adapters_root" for issue in result.issues)
