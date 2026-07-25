from __future__ import annotations

from typing import Any

from cinematic_intelligence_sdk import PromptPackage, PromptScore, PromptSourceContext
from config_sdk import PROMPT_TRANSLATOR_REGISTRY

from .compression import PromptCompressor
from .optimizer import NegativePromptBuilder, PromptOptimizer
from .scoring import PromptScorer
from .versioning import PromptVersioning

_DEFAULT_MAX_WORDS = 60


class PromptIntelligenceEngine:
    """Facade tying together PromptOptimizer, NegativePromptBuilder,
    PromptCompressor, PromptScorer, PromptVersioning, and the
    IPromptTranslator plugin registry - the single entry point a caller
    (a future ProjectLifecycle integration) uses to turn a shot plus
    resolved project memory into a PromptPackage ready for the Render
    Configuration Compiler to fill a RenderSpec's positive_prompt/
    negative_prompt. Never hands a raw, unenriched prompt anywhere -
    see docs/adr/0013-cinematic-intelligence-layer.md."""

    def __init__(self) -> None:
        self._optimizer = PromptOptimizer()
        self._negative_builder = NegativePromptBuilder()
        self._compressor = PromptCompressor()
        self._scorer = PromptScorer()
        self._versioning = PromptVersioning()

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
        extra_negative_terms: list[str] | None = None,
        max_words: int | None = _DEFAULT_MAX_WORDS,
    ) -> dict[str, Any]:
        version = self._versioning.next_version(shot_id)
        package = self._optimizer.build(
            project_id,
            shot_id,
            shot_description,
            characters=characters,
            objects=objects,
            environment=environment,
            style_lock=style_lock,
            camera_notes=camera_notes,
            continuity_notes=continuity_notes,
            version=version,
        )
        if extra_negative_terms:
            package["negative_prompt"] = self._negative_builder.build(extra_negative_terms)
        if max_words is not None:
            package = self._compressor.compress(package, max_words=max_words)

        required_terms = self._required_terms(characters, objects, environment, style_lock)
        package["score"] = self._scorer.score(package, required_terms=required_terms)
        return self._versioning.record(package)

    def translate(self, package: dict[str, Any], engine_id: str) -> dict[str, Any]:
        translator = PROMPT_TRANSLATOR_REGISTRY.create(engine_id)
        translated = translator.translate(prompt_package_from_dict(package))
        return prompt_package_to_dict(translated)

    def compress(self, package: dict[str, Any], max_words: int = _DEFAULT_MAX_WORDS) -> dict[str, Any]:
        return self._compressor.compress(package, max_words=max_words)

    def score(self, package: dict[str, Any], required_terms: list[str] | None = None) -> dict[str, float]:
        return self._scorer.score(package, required_terms=required_terms)

    def history(self, shot_id: str) -> list[dict[str, Any]]:
        return self._versioning.history(shot_id)

    def _required_terms(
        self,
        characters: list[dict[str, Any]] | None,
        objects: list[dict[str, Any]] | None,
        environment: dict[str, Any] | None,
        style_lock: dict[str, Any] | None,
    ) -> list[str]:
        terms: list[str] = [c["display_name"] for c in characters or []]
        terms.extend(o["name"] for o in objects or [])
        if environment:
            terms.append(environment["name"])
        if style_lock and (style_lock.get("base_style") or {}).get("visual_style"):
            terms.append(style_lock["base_style"]["visual_style"])
        return terms


def prompt_package_from_dict(d: dict[str, Any]) -> PromptPackage:
    """Converts a schema-validated prompt_package dict into the
    PromptPackage dataclass IPromptTranslator plugins require - the same
    dict->dataclass boundary pattern FfmpegCompositor uses for Timeline
    (ADR 0009/0012)."""
    source_context = d.get("source_context") or {}
    score = d.get("score")
    return PromptPackage(
        schema_version=d["schema_version"],
        prompt_id=d["prompt_id"],
        project_id=d["project_id"],
        shot_id=d["shot_id"],
        version=d["version"],
        positive_prompt=d["positive_prompt"],
        negative_prompt=d["negative_prompt"],
        source_context=PromptSourceContext(
            character_ids=tuple(source_context.get("character_ids", ())),
            object_ids=tuple(source_context.get("object_ids", ())),
            environment_id=source_context.get("environment_id"),
            style_lock_id=source_context.get("style_lock_id"),
            camera_notes=source_context.get("camera_notes"),
            continuity_notes=source_context.get("continuity_notes"),
        ),
        engine_id=d.get("engine_id"),
        translated_prompt=d.get("translated_prompt"),
        compressed=d.get("compressed", False),
        score=PromptScore(**score) if score else None,
        created_at=d.get("created_at"),
    )


def prompt_package_to_dict(package: PromptPackage) -> dict[str, Any]:
    source_context: dict[str, Any] = {}
    sc = package.source_context
    if sc.character_ids:
        source_context["character_ids"] = list(sc.character_ids)
    if sc.object_ids:
        source_context["object_ids"] = list(sc.object_ids)
    if sc.environment_id:
        source_context["environment_id"] = sc.environment_id
    if sc.style_lock_id:
        source_context["style_lock_id"] = sc.style_lock_id
    if sc.camera_notes:
        source_context["camera_notes"] = sc.camera_notes
    if sc.continuity_notes:
        source_context["continuity_notes"] = sc.continuity_notes

    result: dict[str, Any] = {
        "schema_version": package.schema_version,
        "prompt_id": package.prompt_id,
        "project_id": package.project_id,
        "shot_id": package.shot_id,
        "version": package.version,
        "positive_prompt": package.positive_prompt,
        "negative_prompt": package.negative_prompt,
        "source_context": source_context,
        "compressed": package.compressed,
    }
    if package.engine_id:
        result["engine_id"] = package.engine_id
    if package.translated_prompt:
        result["translated_prompt"] = package.translated_prompt
    if package.score:
        result["score"] = {
            "adherence_estimate": package.score.adherence_estimate,
            "length_score": package.score.length_score,
            "redundancy_score": package.score.redundancy_score,
            "overall": package.score.overall,
        }
    if package.created_at:
        result["created_at"] = package.created_at
    return result
