"""CharacterConsistencyEngine (services/cinematic-intelligence): creates
immutable CharacterIdentityProfiles once, reused (never regenerated) by
every shot referencing the same character_id."""

from __future__ import annotations

import pytest
from cinematic_intelligence.character_consistency import (
    CharacterConsistencyEngine,
    CharacterConsistencyEngineError,
)

IDENTITY = {"face_description": "oval face, freckles", "age_range": "adult", "skin_tone": "tan"}


def test_establish_creates_locked_profile():
    engine = CharacterConsistencyEngine()
    profile = engine.establish("proj_1", "Alice", IDENTITY, character_id="char_alice")

    assert profile["character_id"] == "char_alice"
    assert profile["display_name"] == "Alice"
    assert profile["locked"] is True
    assert profile["identity"] == IDENTITY


def test_get_reuses_the_same_profile_object():
    engine = CharacterConsistencyEngine()
    created = engine.establish("proj_1", "Alice", IDENTITY, character_id="char_alice")
    fetched = engine.get("char_alice")

    assert fetched == created


def test_establish_twice_for_same_character_id_raises():
    engine = CharacterConsistencyEngine()
    engine.establish("proj_1", "Alice", IDENTITY, character_id="char_alice")

    with pytest.raises(CharacterConsistencyEngineError, match="already exists"):
        engine.establish("proj_1", "Alice", IDENTITY, character_id="char_alice")


def test_get_unknown_character_raises():
    engine = CharacterConsistencyEngine()

    with pytest.raises(CharacterConsistencyEngineError, match="No CharacterIdentityProfile"):
        engine.get("char_unknown")


def test_exists():
    engine = CharacterConsistencyEngine()
    assert engine.exists("char_alice") is False
    engine.establish("proj_1", "Alice", IDENTITY, character_id="char_alice")
    assert engine.exists("char_alice") is True


def test_multiple_characters_supported_independently():
    engine = CharacterConsistencyEngine()
    engine.establish("proj_1", "Alice", IDENTITY, character_id="char_alice")
    engine.establish(
        "proj_1",
        "Bob",
        {"face_description": "square jaw", "age_range": "adult", "skin_tone": "pale"},
        character_id="char_bob",
    )

    profiles = engine.list_for_project("proj_1")
    assert {p["character_id"] for p in profiles} == {"char_alice", "char_bob"}


def test_list_for_project_scopes_by_project():
    engine = CharacterConsistencyEngine()
    engine.establish("proj_1", "Alice", IDENTITY, character_id="char_alice")
    engine.establish("proj_2", "Carol", IDENTITY, character_id="char_carol")

    assert [p["character_id"] for p in engine.list_for_project("proj_1")] == ["char_alice"]


def test_auto_generated_character_id():
    engine = CharacterConsistencyEngine()
    profile = engine.establish("proj_1", "Alice", IDENTITY)
    assert profile["character_id"].startswith("char_")


def test_lora_binding_recorded_but_not_required():
    engine = CharacterConsistencyEngine()
    profile = engine.establish(
        "proj_1",
        "Alice",
        IDENTITY,
        character_id="char_alice",
        lora_binding={"lora_id": "lora_alice_v1", "weight": 0.8},
    )
    assert profile["lora_binding"] == {"lora_id": "lora_alice_v1", "weight": 0.8}


def test_expression_bank_and_reference_images_and_seed_recorded():
    engine = CharacterConsistencyEngine()
    profile = engine.establish(
        "proj_1",
        "Alice",
        IDENTITY,
        character_id="char_alice",
        expression_bank=[{"expression": "smiling", "reference_asset_id": "asset_1"}],
        reference_image_ids=["asset_1", "asset_2"],
        consistency_seed=42,
    )
    assert profile["expression_bank"][0]["expression"] == "smiling"
    assert profile["reference_image_ids"] == ["asset_1", "asset_2"]
    assert profile["consistency_seed"] == 42


def test_invalid_identity_fails_schema_validation():
    engine = CharacterConsistencyEngine()
    with pytest.raises(CharacterConsistencyEngineError, match="failed validation"):
        engine.establish("proj_1", "Alice", {"face_description": "oval face"}, character_id="char_alice")
