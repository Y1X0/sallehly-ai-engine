from __future__ import annotations

from typing import Any

import schemas

from ._util import new_id, now_iso


class CharacterConsistencyEngineError(Exception):
    """Raised when a caller tries to re-establish an existing character_id,
    look up one that was never established, or an assembled
    CharacterIdentityProfile fails schema validation."""


class CharacterConsistencyEngine:
    """Creates and reuses CharacterIdentityProfiles
    (character_identity_profile.schema.json) - one per character, created
    once via `establish()` and never regenerated. Every shot referencing
    the same character_id calls `get()` to reuse the exact same face/
    hair/clothing/accessories/proportions/age/skin-tone description
    instead of re-describing the character from scratch, which is what
    keeps a character looking like the same person across every shot and
    scene in a project (see docs/adr/0013-cinematic-intelligence-layer.md).

    Multiple characters are supported simply by using distinct
    character_ids - nothing here assumes a project has exactly one.
    `lora_binding` is recorded on the profile but not applied by any
    engine adapter (see cinematic_intelligence_sdk.LoraBinding /
    IReferenceConditioningAdapter for why that's prepared, not
    implemented, in Phase 7).
    """

    def __init__(self) -> None:
        self._profiles: dict[str, dict[str, Any]] = {}

    def establish(
        self,
        project_id: str,
        display_name: str,
        identity: dict[str, Any],
        *,
        character_id: str | None = None,
        expression_bank: list[dict[str, Any]] | None = None,
        reference_image_ids: list[str] | None = None,
        consistency_seed: int | None = None,
        lora_binding: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        character_id = character_id or new_id("char")
        if character_id in self._profiles:
            raise CharacterConsistencyEngineError(
                f"CharacterIdentityProfile {character_id} already exists - "
                "profiles are immutable, reuse it via get() instead of "
                "re-establishing it"
            )

        profile: dict[str, Any] = {
            "schema_version": "1.0",
            "character_id": character_id,
            "project_id": project_id,
            "display_name": display_name,
            "identity": identity,
            "locked": True,
            "created_at": now_iso(),
        }
        if expression_bank:
            profile["expression_bank"] = expression_bank
        if reference_image_ids:
            profile["reference_image_ids"] = reference_image_ids
        if consistency_seed is not None:
            profile["consistency_seed"] = consistency_seed
        if lora_binding:
            profile["lora_binding"] = lora_binding

        try:
            schemas.validate(profile, "character_identity_profile")
        except Exception as exc:  # noqa: BLE001 - re-raised as a domain error
            raise CharacterConsistencyEngineError(
                f"Assembled CharacterIdentityProfile failed validation: {exc}"
            ) from exc

        self._profiles[character_id] = profile
        return profile

    def get(self, character_id: str) -> dict[str, Any]:
        try:
            return self._profiles[character_id]
        except KeyError:
            raise CharacterConsistencyEngineError(
                f"No CharacterIdentityProfile for character_id {character_id!r} - "
                "it must be established before it can be reused"
            ) from None

    def exists(self, character_id: str) -> bool:
        return character_id in self._profiles

    def list_for_project(self, project_id: str) -> list[dict[str, Any]]:
        return [p for p in self._profiles.values() if p["project_id"] == project_id]
