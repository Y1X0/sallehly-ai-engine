"""Phase 9 Preparation: the Model Registry - version management,
checkpoint metadata, promotion, rollback, and capability-manifest
compatibility validation. Real, disk-backed, CPU-only - no GPU or model
weights ever touched, only metadata about them. See
docs/adr/0021-phase9-preparation.md.
"""

from __future__ import annotations

import pytest
from training import (
    FilesystemModelRegistry,
    InvalidPromotionTransitionError,
    ModelRegistryError,
    ModelVersionRecord,
    PromotionStatus,
    UnknownModelVersionError,
    assert_valid_transition,
    validate_capability_manifest,
)
from video_engine_sdk import CapabilityManifest


def _manifest(**overrides) -> CapabilityManifest:
    base = dict(
        engine_id="sallehly-v1",
        engine_version="0.1.0",
        modes=["text_to_video"],
        max_shot_duration_sec=8.0,
        min_shot_duration_sec=1.0,
        resolutions=["1280x720"],
        fps_options=[24],
        motion_strength_range=(0.0, 100.0),
        license="proprietary",
        min_vram_gb=24.0,
    )
    base.update(overrides)
    return CapabilityManifest(**base)


def _version(version_id: str = "v1", **overrides) -> ModelVersionRecord:
    base = dict(
        version_id=version_id,
        base_model_id="wan2.1",
        checkpoint_id=f"ckpt_{version_id}",
        training_run_id=f"run_{version_id}",
        dataset_version="ds_1",
        capability_manifest=_manifest(),
    )
    base.update(overrides)
    return ModelVersionRecord(**base)


# --- ModelVersionRecord --------------------------------------------------


def test_model_version_record_round_trips_through_dict_including_manifest():
    record = _version()
    restored = ModelVersionRecord.from_dict(record.to_dict())
    assert restored.version_id == record.version_id
    assert restored.capability_manifest == record.capability_manifest
    assert restored.status == PromotionStatus.STAGING


# --- Promotion state machine ----------------------------------------------


@pytest.mark.parametrize(
    "current,target",
    [
        (PromotionStatus.STAGING, PromotionStatus.CANARY),
        (PromotionStatus.STAGING, PromotionStatus.REJECTED),
        (PromotionStatus.CANARY, PromotionStatus.PRODUCTION),
        (PromotionStatus.CANARY, PromotionStatus.STAGING),
        (PromotionStatus.CANARY, PromotionStatus.REJECTED),
        (PromotionStatus.PRODUCTION, PromotionStatus.ARCHIVED),
        (PromotionStatus.ARCHIVED, PromotionStatus.CANARY),
    ],
)
def test_assert_valid_transition_allows_the_defined_forward_moves(current, target):
    assert_valid_transition(current, target)  # must not raise


@pytest.mark.parametrize(
    "current,target",
    [
        (PromotionStatus.STAGING, PromotionStatus.PRODUCTION),  # skips canary
        (PromotionStatus.REJECTED, PromotionStatus.STAGING),  # terminal state
        (PromotionStatus.PRODUCTION, PromotionStatus.STAGING),  # backward without archiving first
    ],
)
def test_assert_valid_transition_rejects_invalid_moves(current, target):
    with pytest.raises(InvalidPromotionTransitionError):
        assert_valid_transition(current, target)


# --- validate_capability_manifest ----------------------------------------


def test_validate_capability_manifest_accepts_a_sane_manifest():
    result = validate_capability_manifest(_manifest())
    assert result.valid is True


@pytest.mark.parametrize(
    "overrides",
    [
        {"engine_id": ""},
        {"modes": []},
        {"modes": ["not-a-real-mode"]},
        {"min_shot_duration_sec": 0.0},
        {"max_shot_duration_sec": 0.5, "min_shot_duration_sec": 1.0},
        {"resolutions": []},
        {"resolutions": ["not-a-resolution"]},
        {"fps_options": []},
        {"fps_options": [-1]},
        {"motion_strength_range": (100.0, 0.0)},
        {"min_vram_gb": -1.0},
    ],
)
def test_validate_capability_manifest_rejects_structural_problems(overrides):
    result = validate_capability_manifest(_manifest(**overrides))
    assert result.valid is False


def test_validate_capability_manifest_warns_but_does_not_fail_on_missing_license():
    result = validate_capability_manifest(_manifest(license=None))
    assert result.valid is True
    assert any(i.field == "license" and i.severity == "warning" for i in result.issues)


# --- FilesystemModelRegistry ----------------------------------------------


def test_register_and_get(tmp_path):
    registry = FilesystemModelRegistry(tmp_path)
    registry.register(_version("v1"))

    record = registry.get("v1")
    assert record is not None
    assert record.status == PromotionStatus.STAGING
    assert registry.get("does-not-exist") is None


def test_register_duplicate_version_id_raises(tmp_path):
    registry = FilesystemModelRegistry(tmp_path)
    registry.register(_version("v1"))
    with pytest.raises(ModelRegistryError):
        registry.register(_version("v1"))


def test_promote_unknown_version_raises(tmp_path):
    registry = FilesystemModelRegistry(tmp_path)
    with pytest.raises(UnknownModelVersionError):
        registry.promote("does-not-exist", PromotionStatus.CANARY)


def test_promote_full_path_to_production(tmp_path):
    registry = FilesystemModelRegistry(tmp_path)
    registry.register(_version("v1"))

    registry.promote("v1", PromotionStatus.CANARY)
    record = registry.promote("v1", PromotionStatus.PRODUCTION)

    assert record.status == PromotionStatus.PRODUCTION
    assert registry.get_production().version_id == "v1"


def test_promote_rejects_skipping_canary(tmp_path):
    registry = FilesystemModelRegistry(tmp_path)
    registry.register(_version("v1"))
    with pytest.raises(InvalidPromotionTransitionError):
        registry.promote("v1", PromotionStatus.PRODUCTION)


def test_promote_to_canary_rejects_an_incompatible_manifest(tmp_path):
    registry = FilesystemModelRegistry(tmp_path)
    registry.register(_version("v1", capability_manifest=_manifest(modes=[])))
    with pytest.raises(ModelRegistryError):
        registry.promote("v1", PromotionStatus.CANARY)


def test_promoting_a_second_version_to_production_archives_the_first(tmp_path):
    registry = FilesystemModelRegistry(tmp_path)
    registry.register(_version("v1"))
    registry.register(_version("v2"))

    registry.promote("v1", PromotionStatus.CANARY)
    registry.promote("v1", PromotionStatus.PRODUCTION)

    registry.promote("v2", PromotionStatus.CANARY)
    registry.promote("v2", PromotionStatus.PRODUCTION)

    assert registry.get("v1").status == PromotionStatus.ARCHIVED
    assert registry.get_production().version_id == "v2"


def test_get_production_returns_none_when_nothing_is_promoted(tmp_path):
    registry = FilesystemModelRegistry(tmp_path)
    registry.register(_version("v1"))
    assert registry.get_production() is None


def test_rollback_reverts_to_the_prior_production_version(tmp_path):
    registry = FilesystemModelRegistry(tmp_path)
    registry.register(_version("v1"))
    registry.register(_version("v2"))
    registry.promote("v1", PromotionStatus.CANARY)
    registry.promote("v1", PromotionStatus.PRODUCTION)
    registry.promote("v2", PromotionStatus.CANARY)
    registry.promote("v2", PromotionStatus.PRODUCTION)

    restored = registry.rollback()

    assert restored.version_id == "v1"
    assert registry.get("v1").status == PromotionStatus.PRODUCTION
    assert registry.get("v2").status == PromotionStatus.ARCHIVED
    assert registry.get_production().version_id == "v1"


def test_rollback_with_no_prior_production_returns_none(tmp_path):
    registry = FilesystemModelRegistry(tmp_path)
    registry.register(_version("v1"))
    registry.promote("v1", PromotionStatus.CANARY)
    registry.promote("v1", PromotionStatus.PRODUCTION)

    assert registry.rollback() is None
    assert registry.get_production().version_id == "v1"  # unchanged


def test_registry_persists_across_instances(tmp_path):
    registry = FilesystemModelRegistry(tmp_path)
    registry.register(_version("v1"))
    registry.promote("v1", PromotionStatus.CANARY)
    registry.promote("v1", PromotionStatus.PRODUCTION)

    reopened = FilesystemModelRegistry(tmp_path)
    assert reopened.get_production().version_id == "v1"
    assert len(reopened.list_all()) == 1
