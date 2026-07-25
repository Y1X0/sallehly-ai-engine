from __future__ import annotations

from typing import Any

import schemas

from .._util import new_id, now_iso

_DEFAULT_NEGATIVE_TERMS = (
    "blurry",
    "low quality",
    "distorted anatomy",
    "extra limbs",
    "inconsistent lighting",
    "flickering",
    "warped geometry",
)


class PromptOptimizerError(Exception):
    """Raised when an assembled PromptPackage fails schema validation."""


class PromptOptimizer:
    """Builds a shot's PromptPackage (prompt_package.schema.json) from
    project memory instead of a raw, hand-written prompt: the shot's
    plain-language description is woven together with resolved
    CharacterIdentityProfiles, ObjectProfiles, an EnvironmentProfile, and
    the project's StyleLock, so every generated shot's prompt carries
    the exact same character/object/environment/style language as every
    other shot referencing the same subjects - no "raw prompt" ever
    reaches a RenderSpec on its own. See
    docs/adr/0013-cinematic-intelligence-layer.md."""

    def build(
        self,
        project_id: str,
        shot_id: str,
        shot_description: str,
        *,
        characters: list[dict[str, Any]] | None = None,
        objects: list[dict[str, Any]] | None = None,
        environment: dict[str, Any] | None = None,
        style_lock: dict[str, Any] | None = None,
        camera_notes: str | None = None,
        continuity_notes: str | None = None,
        version: int = 1,
    ) -> dict[str, Any]:
        characters = characters or []
        objects = objects or []
        fragments: list[str] = [shot_description.strip()] if shot_description.strip() else []
        fragments.extend(self._character_fragments(characters))
        fragments.extend(self._object_fragments(objects))
        environment_fragment = self._environment_fragment(environment)
        if environment_fragment:
            fragments.append(environment_fragment)
        style_fragment = self._style_fragment(style_lock)
        if style_fragment:
            fragments.append(style_fragment)
        if camera_notes:
            fragments.append(camera_notes.strip())
        if continuity_notes:
            fragments.append(continuity_notes.strip())

        positive_prompt = ", ".join(f for f in fragments if f)
        negative_prompt = ", ".join(_DEFAULT_NEGATIVE_TERMS)

        source_context: dict[str, Any] = {}
        character_ids = [c["character_id"] for c in characters]
        if character_ids:
            source_context["character_ids"] = character_ids
        object_ids = [o["object_id"] for o in objects]
        if object_ids:
            source_context["object_ids"] = object_ids
        if environment:
            source_context["environment_id"] = environment["environment_id"]
        if style_lock:
            source_context["style_lock_id"] = style_lock["style_lock_id"]
        if camera_notes:
            source_context["camera_notes"] = camera_notes
        if continuity_notes:
            source_context["continuity_notes"] = continuity_notes

        package: dict[str, Any] = {
            "schema_version": "1.0",
            "prompt_id": new_id("prompt"),
            "project_id": project_id,
            "shot_id": shot_id,
            "version": version,
            "positive_prompt": positive_prompt,
            "negative_prompt": negative_prompt,
            "source_context": source_context,
            "created_at": now_iso(),
        }
        try:
            schemas.validate(package, "prompt_package")
        except Exception as exc:  # noqa: BLE001
            raise PromptOptimizerError(f"Assembled PromptPackage failed validation: {exc}") from exc
        return package

    def _character_fragments(self, characters: list[dict[str, Any]]) -> list[str]:
        fragments = []
        for character in characters:
            identity = character["identity"]
            parts = [character["display_name"], identity["face_description"]]
            hair = identity.get("hair") or {}
            hair_bits = [b for b in (hair.get("color"), hair.get("style"), hair.get("length")) if b]
            if hair_bits:
                parts.append(" ".join(hair_bits) + " hair")
            if identity.get("clothing_default"):
                parts.append(f"wearing {identity['clothing_default']}")
            if identity.get("accessories"):
                parts.append(f"with {', '.join(identity['accessories'])}")
            fragments.append(", ".join(parts))
        return fragments

    def _object_fragments(self, objects: list[dict[str, Any]]) -> list[str]:
        fragments = []
        for obj in objects:
            attributes = obj.get("attributes") or {}
            parts = [obj["name"]]
            if attributes.get("colors"):
                parts.append(", ".join(attributes["colors"]))
            if attributes.get("materials"):
                parts.append(", ".join(attributes["materials"]))
            if attributes.get("damage_state") and attributes["damage_state"] != "pristine":
                parts.append(attributes["damage_state"])
            fragments.append(" ".join(parts))
        return fragments

    def _environment_fragment(self, environment: dict[str, Any] | None) -> str | None:
        if not environment:
            return None
        parts = [f"set in {environment['name']}"]
        for field_name in ("weather", "time_of_day", "season", "sky"):
            if environment.get(field_name):
                parts.append(str(environment[field_name]))
        return ", ".join(parts)

    def _style_fragment(self, style_lock: dict[str, Any] | None) -> str | None:
        if not style_lock:
            return None
        parts = []
        base_style = style_lock.get("base_style") or {}
        if base_style.get("visual_style"):
            parts.append(base_style["visual_style"])
        if style_lock.get("film_stock"):
            parts.append(style_lock["film_stock"])
        if style_lock.get("lighting_language"):
            parts.append(style_lock["lighting_language"])
        grain = style_lock.get("grain") or {}
        if grain.get("enabled"):
            parts.append(f"{grain.get('intensity', 'subtle')} film grain")
        bloom = style_lock.get("bloom") or {}
        if bloom.get("enabled"):
            parts.append(f"{bloom.get('intensity', 'subtle')} bloom")
        if style_lock.get("lens_effects"):
            parts.extend(style_lock["lens_effects"])
        parts.append(f"{style_lock.get('depth_of_field_target', 'medium')} depth of field")
        return ", ".join(parts)


class NegativePromptBuilder:
    """Builds a shot's negative prompt from the project's default quality
    baseline plus any extra terms a caller supplies (e.g. terms an
    Automatic Repair Engine strategy adds after a specific defect was
    observed)."""

    def build(self, extra_terms: list[str] | None = None) -> str:
        terms = list(_DEFAULT_NEGATIVE_TERMS)
        for term in extra_terms or []:
            if term not in terms:
                terms.append(term)
        return ", ".join(terms)
