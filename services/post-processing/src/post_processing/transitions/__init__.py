from __future__ import annotations

from config_sdk import TRANSITION_PLUGIN_REGISTRY
from video_composition_sdk import ITransitionPlugin, Transition, TransitionRecipe

from .plugins import (
    CinematicCutPlugin,
    DissolvePlugin,
    FadeInPlugin,
    FadeOutPlugin,
    MatchCutPlugin,
    WhipPanPlugin,
    WipePlugin,
    ZoomPlugin,
)

_BUILTIN_PLUGINS = (
    CinematicCutPlugin,
    FadeInPlugin,
    FadeOutPlugin,
    DissolvePlugin,
    MatchCutPlugin,
    WipePlugin,
    WhipPanPlugin,
    ZoomPlugin,
)


def register_defaults() -> None:
    """Registers every built-in transition plugin into
    TRANSITION_PLUGIN_REGISTRY, keyed by its plugin_id (which matches
    transition.schema.json's `type` enum values). Idempotent - safe to
    call more than once within a process (tests re-importing this
    module, ...), same pattern as
    video_engine_adapter.registry.register_defaults()."""
    for plugin_cls in _BUILTIN_PLUGINS:
        TRANSITION_PLUGIN_REGISTRY.register_if_absent(plugin_cls.plugin_id, plugin_cls)


class TransitionEngine:
    """Resolves a Transition (transition.schema.json) into a
    TransitionRecipe by looking up its plugin in
    TRANSITION_PLUGIN_REGISTRY - `type` is the registry key, except for
    `type="custom"` where `plugin_id` is. Registering a new plugin (built-in
    or custom) is the entire extension mechanism; TransitionEngine itself
    never special-cases any transition type."""

    def resolve(self, transition: Transition) -> TransitionRecipe:
        key = transition.plugin_id if transition.type == "custom" else transition.type
        if key is None:
            raise ValueError("Transition(type='custom') requires plugin_id")
        plugin: ITransitionPlugin = TRANSITION_PLUGIN_REGISTRY.create(key)
        return plugin.resolve(transition)


__all__ = ["TransitionEngine", "register_defaults"]
