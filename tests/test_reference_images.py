"""ReferenceImageEngine (services/cinematic-intelligence): builds
reusable ReferencePackages for characters/objects/environments/style/
pose. prepared_for flags are readiness markers only - no ControlNet/
IP-Adapter conditioning actually runs (see IReferenceConditioningAdapter)."""

from __future__ import annotations

import pytest
from cinematic_intelligence.reference_images import ReferenceImageEngine, ReferenceImageEngineError

IMAGES = [{"asset_id": "asset_1", "role": "primary"}, {"asset_id": "asset_2", "role": "angle"}]


def test_character_package():
    engine = ReferenceImageEngine()
    package = engine.character_package("proj_1", "char_alice", IMAGES)

    assert package["kind"] == "character"
    assert package["subject_id"] == "char_alice"
    assert package["images"] == IMAGES


def test_object_package():
    engine = ReferenceImageEngine()
    package = engine.object_package("proj_1", "obj_car", IMAGES)
    assert package["kind"] == "object"
    assert package["subject_id"] == "obj_car"


def test_environment_package():
    engine = ReferenceImageEngine()
    package = engine.environment_package("proj_1", "env_street", IMAGES)
    assert package["kind"] == "environment"
    assert package["subject_id"] == "env_street"


def test_style_package_has_no_subject():
    engine = ReferenceImageEngine()
    package = engine.style_package("proj_1", IMAGES)
    assert package["kind"] == "style"
    assert "subject_id" not in package


def test_pose_package_has_no_subject():
    engine = ReferenceImageEngine()
    package = engine.pose_package("proj_1", IMAGES)
    assert package["kind"] == "pose"


def test_character_kind_requires_subject_id():
    engine = ReferenceImageEngine()
    with pytest.raises(ReferenceImageEngineError, match="requires a subject_id"):
        engine.create("proj_1", "character", IMAGES)


def test_prepared_for_defaults_to_false():
    engine = ReferenceImageEngine()
    package = engine.character_package("proj_1", "char_alice", IMAGES)
    assert "prepared_for" not in package or package["prepared_for"] == {"controlnet": False, "ip_adapter": False}


def test_prepared_for_can_be_set():
    engine = ReferenceImageEngine()
    package = engine.create(
        "proj_1", "character", IMAGES, subject_id="char_alice", prepared_for={"controlnet": True}
    )
    assert package["prepared_for"]["controlnet"] is True


def test_empty_images_fails_schema_validation():
    engine = ReferenceImageEngine()
    with pytest.raises(ReferenceImageEngineError, match="failed validation"):
        engine.character_package("proj_1", "char_alice", [])


def test_get_by_package_id():
    engine = ReferenceImageEngine()
    created = engine.character_package("proj_1", "char_alice", IMAGES)
    fetched = engine.get(created["package_id"])
    assert fetched == created


def test_get_unknown_package_raises():
    engine = ReferenceImageEngine()
    with pytest.raises(ReferenceImageEngineError, match="No ReferencePackage"):
        engine.get("ref_unknown")


def test_list_for_subject():
    engine = ReferenceImageEngine()
    engine.character_package("proj_1", "char_alice", IMAGES)
    engine.character_package("proj_1", "char_bob", IMAGES)
    packages = engine.list_for_subject("proj_1", "char_alice")
    assert len(packages) == 1
    assert packages[0]["subject_id"] == "char_alice"


def test_list_for_project():
    engine = ReferenceImageEngine()
    engine.character_package("proj_1", "char_alice", IMAGES)
    engine.style_package("proj_1", IMAGES)
    engine.style_package("proj_2", IMAGES)
    assert len(engine.list_for_project("proj_1")) == 2
