"""Transition Engine (services/post-processing/transitions): every
built-in plugin resolves to a correct TransitionRecipe, plus custom
plugin registration through TRANSITION_PLUGIN_REGISTRY. No ffmpeg
required - resolves to a recipe, doesn't run ffmpeg itself."""

from __future__ import annotations

import pytest
from config_sdk import TRANSITION_PLUGIN_REGISTRY
from post_processing.transitions import TransitionEngine, register_defaults
from video_composition_sdk import ITransitionPlugin, Transition, TransitionRecipe


@pytest.fixture(autouse=True)
def _register_builtins():
    register_defaults()


def test_cinematic_cut_resolves_to_hard_cut():
    recipe = TransitionEngine().resolve(Transition(type="cinematic_cut"))
    assert recipe.mode == "hard_cut"


@pytest.mark.parametrize(
    "transition_type,expected_xfade",
    [
        ("dissolve", "dissolve"),
        ("match_cut", "fade"),
        ("wipe", "wipeleft"),
        ("whip_pan", "hblur"),
        ("zoom", "zoomin"),
    ],
)
def test_xfade_plugins_map_to_real_ffmpeg_presets(transition_type, expected_xfade):
    recipe = TransitionEngine().resolve(Transition(type=transition_type))
    assert recipe.mode == "xfade"
    assert recipe.xfade_transition == expected_xfade
    assert recipe.duration_sec > 0


def test_wipe_plugin_direction_param_selects_matching_preset():
    engine = TransitionEngine()
    for direction, expected in [("left", "wipeleft"), ("right", "wiperight"), ("up", "wipeup"), ("down", "wipedown")]:
        recipe = engine.resolve(Transition(type="wipe", params={"direction": direction}))
        assert recipe.xfade_transition == expected


def test_fade_in_and_fade_out_resolve_to_single_clip_modes():
    engine = TransitionEngine()
    fade_in = engine.resolve(Transition(type="fade_in"))
    assert fade_in.mode == "fade_from_black"

    fade_out = engine.resolve(Transition(type="fade_out"))
    assert fade_out.mode == "fade_to_black"


def test_explicit_duration_overrides_the_plugin_default():
    recipe = TransitionEngine().resolve(Transition(type="dissolve", duration_sec=1.25))
    assert recipe.duration_sec == 1.25


def test_unknown_type_raises_a_clear_registry_error():
    with pytest.raises(KeyError, match="unknown key 'not_a_real_type'"):
        TransitionEngine().resolve(Transition(type="not_a_real_type"))


def test_custom_plugin_requires_plugin_id():
    with pytest.raises(ValueError, match="plugin_id"):
        TransitionEngine().resolve(Transition(type="custom"))


def test_custom_plugin_registers_and_resolves():
    class GlitchPlugin(ITransitionPlugin):
        plugin_id = "glitch"

        def resolve(self, transition: Transition) -> TransitionRecipe:
            return TransitionRecipe(mode="xfade", xfade_transition="pixelize", duration_sec=0.2)

    TRANSITION_PLUGIN_REGISTRY.register_if_absent("glitch", GlitchPlugin)
    recipe = TransitionEngine().resolve(Transition(type="custom", plugin_id="glitch"))
    assert recipe.xfade_transition == "pixelize"


def test_register_defaults_is_idempotent():
    register_defaults()
    register_defaults()  # should not raise
    assert "dissolve" in TRANSITION_PLUGIN_REGISTRY
