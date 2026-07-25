"""Prompt Intelligence Engine (services/cinematic-intelligence): builds a
shot's PromptPackage from project memory rather than a raw prompt, plus
the NegativePromptBuilder/PromptCompressor/PromptScorer/PromptVersioning
components and the IPromptTranslator plugin registry."""

from __future__ import annotations

import pytest
from cinematic_intelligence.prompt_intelligence import (
    NegativePromptBuilder,
    PromptCompressor,
    PromptIntelligenceEngine,
    PromptOptimizer,
    PromptOptimizerError,
    PromptScorer,
    PromptVersioning,
    register_defaults,
)
from cinematic_intelligence.prompt_intelligence.engine import prompt_package_from_dict, prompt_package_to_dict
from config_sdk import PROMPT_TRANSLATOR_REGISTRY

CHARACTER = {
    "character_id": "char_alice",
    "display_name": "Alice",
    "identity": {
        "face_description": "oval face, freckles",
        "age_range": "adult",
        "skin_tone": "tan",
        "hair": {"color": "red", "style": "curly", "length": "long"},
        "clothing_default": "a green jacket",
        "accessories": ["a silver necklace"],
    },
}
OBJECT = {"object_id": "obj_car", "name": "car", "attributes": {"colors": ["red"], "damage_state": "pristine"}}
ENVIRONMENT = {"environment_id": "env_street", "name": "Main Street", "weather": "clear", "time_of_day": "morning"}
STYLE_LOCK = {
    "style_lock_id": "style_1",
    "base_style": {"visual_style": "cinematic photorealistic"},
    "lighting_language": "warm highlights",
    "depth_of_field_target": "shallow",
}


@pytest.fixture(autouse=True)
def _register():
    register_defaults()


class TestPromptOptimizer:
    def test_build_weaves_in_all_context(self):
        optimizer = PromptOptimizer()
        package = optimizer.build(
            "proj_1",
            "shot_1",
            "Alice walks into the room",
            characters=[CHARACTER],
            objects=[OBJECT],
            environment=ENVIRONMENT,
            style_lock=STYLE_LOCK,
        )
        assert "Alice walks into the room" in package["positive_prompt"]
        assert "Alice" in package["positive_prompt"]
        assert "car" in package["positive_prompt"]
        assert "Main Street" in package["positive_prompt"]
        assert "cinematic photorealistic" in package["positive_prompt"]
        assert package["source_context"]["character_ids"] == ["char_alice"]
        assert package["source_context"]["style_lock_id"] == "style_1"

    def test_build_with_no_context_uses_only_description(self):
        optimizer = PromptOptimizer()
        package = optimizer.build("proj_1", "shot_1", "A quiet empty room")
        assert package["positive_prompt"] == "A quiet empty room"
        assert package["source_context"] == {}

    def test_build_weaves_in_camera_and_continuity_notes(self):
        optimizer = PromptOptimizer()
        package = optimizer.build(
            "proj_1",
            "shot_1",
            "Alice walks in",
            camera_notes="slow dolly in",
            continuity_notes="matches previous shot's blocking",
        )
        assert "slow dolly in" in package["positive_prompt"]
        assert "matches previous shot's blocking" in package["positive_prompt"]
        assert package["source_context"]["camera_notes"] == "slow dolly in"
        assert package["source_context"]["continuity_notes"] == "matches previous shot's blocking"

    def test_build_weaves_in_object_materials_and_full_style_lock(self):
        optimizer = PromptOptimizer()
        object_with_materials = {
            "object_id": "obj_car",
            "name": "car",
            "attributes": {"materials": ["chrome", "leather"], "colors": ["red"], "damage_state": "scratched"},
        }
        full_style_lock = {
            "style_lock_id": "style_1",
            "base_style": {"visual_style": "cinematic photorealistic"},
            "film_stock": "35mm film emulation",
            "lighting_language": "warm highlights",
            "grain": {"enabled": True, "intensity": "medium"},
            "bloom": {"enabled": True, "intensity": "subtle"},
            "lens_effects": ["anamorphic flares"],
        }
        package = optimizer.build(
            "proj_1", "shot_1", "A car chase", objects=[object_with_materials], style_lock=full_style_lock
        )
        assert "chrome, leather" in package["positive_prompt"]
        assert "scratched" in package["positive_prompt"]
        assert "35mm film emulation" in package["positive_prompt"]
        assert "medium film grain" in package["positive_prompt"]
        assert "subtle bloom" in package["positive_prompt"]
        assert "anamorphic flares" in package["positive_prompt"]

    def test_build_is_schema_valid(self):
        optimizer = PromptOptimizer()
        package = optimizer.build("proj_1", "shot_1", "Establishing shot")
        assert package["schema_version"] == "1.0"
        assert package["version"] == 1

    def test_build_raises_on_bad_version_type(self):
        optimizer = PromptOptimizer()
        with pytest.raises(PromptOptimizerError):
            optimizer.build("proj_1", "shot_1", "test", version="not-an-int")


class TestNegativePromptBuilder:
    def test_default_terms(self):
        builder = NegativePromptBuilder()
        negative = builder.build()
        assert "blurry" in negative
        assert "low quality" in negative

    def test_extra_terms_appended(self):
        builder = NegativePromptBuilder()
        negative = builder.build(extra_terms=["identity drift"])
        assert "identity drift" in negative

    def test_duplicate_extra_terms_not_repeated(self):
        builder = NegativePromptBuilder()
        negative = builder.build(extra_terms=["blurry"])
        assert negative.count("blurry") == 1


class TestPromptCompressor:
    def test_short_prompt_unchanged(self):
        compressor = PromptCompressor()
        package = {"positive_prompt": "a short prompt", "compressed": False}
        result = compressor.compress(package, max_words=60)
        assert result == package

    def test_deduplicates_repeated_fragments(self):
        compressor = PromptCompressor()
        package = {"positive_prompt": ", ".join(["fragment"] * 80), "compressed": False}
        result = compressor.compress(package, max_words=60)
        assert result["positive_prompt"] == "fragment"
        assert result["compressed"] is True

    def test_truncates_when_still_over_budget(self):
        compressor = PromptCompressor()
        package = {"positive_prompt": ", ".join(f"word{i}" for i in range(80)), "compressed": False}
        result = compressor.compress(package, max_words=10)
        assert result["compressed"] is True
        assert result["positive_prompt"].endswith("...")
        assert len(result["positive_prompt"].split()) == 10


class TestPromptScorer:
    def test_ideal_length_scores_one(self):
        scorer = PromptScorer()
        package = {"positive_prompt": " ".join(["word"] * 30)}
        scores = scorer.score(package)
        assert scores["length_score"] == 1.0

    def test_too_short_penalized(self):
        scorer = PromptScorer()
        package = {"positive_prompt": "one two three"}
        scores = scorer.score(package)
        assert scores["length_score"] < 1.0

    def test_too_long_penalized(self):
        scorer = PromptScorer()
        package = {"positive_prompt": " ".join(["word"] * 200)}
        scores = scorer.score(package)
        assert scores["length_score"] < 1.0

    def test_redundancy_detects_repeats(self):
        scorer = PromptScorer()
        package = {"positive_prompt": "cat cat cat cat cat"}
        scores = scorer.score(package)
        assert scores["redundancy_score"] < 1.0

    def test_redundancy_score_zero_for_prompt_with_no_words(self):
        scorer = PromptScorer()
        scores = scorer.score({"positive_prompt": "!!! ,,, ---"})
        assert scores["redundancy_score"] == 0.0

    def test_no_redundancy_when_all_unique(self):
        scorer = PromptScorer()
        package = {"positive_prompt": "a b c d e"}
        scores = scorer.score(package)
        assert scores["redundancy_score"] == 1.0

    def test_adherence_no_required_terms_is_perfect(self):
        scorer = PromptScorer()
        scores = scorer.score({"positive_prompt": "anything"}, required_terms=None)
        assert scores["adherence_estimate"] == 1.0

    def test_adherence_partial_match(self):
        scorer = PromptScorer()
        scores = scorer.score({"positive_prompt": "Alice in the street"}, required_terms=["Alice", "car"])
        assert scores["adherence_estimate"] == 0.5

    def test_overall_is_weighted_combination(self):
        scorer = PromptScorer()
        scores = scorer.score({"positive_prompt": " ".join(["word"] * 30)}, required_terms=[])
        assert scores["overall"] == pytest.approx(
            0.5 * scores["adherence_estimate"] + 0.25 * scores["length_score"] + 0.25 * scores["redundancy_score"],
            abs=1e-3,
        )


class TestPromptVersioning:
    def test_first_version_is_one(self):
        versioning = PromptVersioning()
        assert versioning.next_version("shot_1") == 1

    def test_record_and_next_version_increments(self):
        versioning = PromptVersioning()
        versioning.record({"shot_id": "shot_1", "version": 1})
        assert versioning.next_version("shot_1") == 2

    def test_history_and_latest(self):
        versioning = PromptVersioning()
        versioning.record({"shot_id": "shot_1", "version": 1})
        versioning.record({"shot_id": "shot_1", "version": 2})
        assert len(versioning.history("shot_1")) == 2
        assert versioning.latest("shot_1")["version"] == 2

    def test_latest_none_when_no_history(self):
        versioning = PromptVersioning()
        assert versioning.latest("shot_unknown") is None


class TestPromptTranslators:
    @pytest.mark.parametrize("engine_id", ["wan2.1", "veo", "runway", "luma", "kling", "pika"])
    def test_all_builtin_engines_registered(self, engine_id):
        assert engine_id in PROMPT_TRANSLATOR_REGISTRY

    def test_translate_sets_engine_id_and_translated_prompt(self):
        engine = PromptIntelligenceEngine()
        package = engine.build("proj_1", "shot_1", "A calm morning")
        translated = engine.translate(package, "wan2.1")
        assert translated["engine_id"] == "wan2.1"
        assert translated["positive_prompt"] in translated["translated_prompt"]
        assert translated["translated_prompt"] != translated["positive_prompt"]

    def test_translate_never_mutates_source_positive_prompt(self):
        engine = PromptIntelligenceEngine()
        package = engine.build("proj_1", "shot_1", "A calm morning")
        translated = engine.translate(package, "veo")
        assert translated["positive_prompt"] == package["positive_prompt"]

    def test_round_trip_dict_dataclass_conversion(self):
        engine = PromptIntelligenceEngine()
        package = engine.build(
            "proj_1",
            "shot_1",
            "A calm morning",
            characters=[CHARACTER],
            objects=[OBJECT],
            environment=ENVIRONMENT,
            style_lock=STYLE_LOCK,
            camera_notes="slow push in",
            continuity_notes="matches prior blocking",
        )
        dataclass_package = prompt_package_from_dict(package)
        round_tripped = prompt_package_to_dict(dataclass_package)
        assert round_tripped["positive_prompt"] == package["positive_prompt"]
        assert round_tripped["source_context"] == package["source_context"]


class TestPromptIntelligenceEngineFacade:
    def test_build_bumps_version_across_calls(self):
        engine = PromptIntelligenceEngine()
        first = engine.build("proj_1", "shot_1", "Alice enters")
        second = engine.build("proj_1", "shot_1", "Alice sits down")
        assert first["version"] == 1
        assert second["version"] == 2
        assert len(engine.history("shot_1")) == 2

    def test_build_attaches_score(self):
        engine = PromptIntelligenceEngine()
        package = engine.build("proj_1", "shot_1", "Alice enters", characters=[CHARACTER])
        assert 0.0 <= package["score"]["overall"] <= 1.0

    def test_build_uses_default_negative_prompt(self):
        engine = PromptIntelligenceEngine()
        package = engine.build("proj_1", "shot_1", "Alice enters")
        assert "blurry" in package["negative_prompt"]

    def test_build_with_extra_negative_terms(self):
        engine = PromptIntelligenceEngine()
        package = engine.build("proj_1", "shot_1", "Alice enters", extra_negative_terms=["stiff motion"])
        assert "stiff motion" in package["negative_prompt"]

    def test_build_compresses_long_prompt(self):
        engine = PromptIntelligenceEngine()
        long_description = ", ".join(f"detail{i}" for i in range(100))
        package = engine.build("proj_1", "shot_1", long_description, max_words=20)
        assert package["compressed"] is True

    def test_build_without_compression_when_max_words_none(self):
        engine = PromptIntelligenceEngine()
        long_description = ", ".join(f"detail{i}" for i in range(100))
        package = engine.build("proj_1", "shot_1", long_description, max_words=None)
        assert package.get("compressed", False) is False

    def test_compress_and_score_delegate_correctly(self):
        engine = PromptIntelligenceEngine()
        package = engine.build("proj_1", "shot_1", "Alice enters")
        assert engine.compress(package, max_words=1000) == package
        assert "overall" in engine.score(package)
