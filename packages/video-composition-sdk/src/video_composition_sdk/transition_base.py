from __future__ import annotations

from abc import ABC, abstractmethod

from .types import Transition, TransitionRecipe


class ITransitionPlugin(ABC):
    """One entry in the Transition Engine's plugin registry
    (config_sdk.registry.TRANSITION_PLUGIN_REGISTRY, key = Transition.type
    or, for type="custom", Transition.plugin_id). Resolves a Transition
    into a TransitionRecipe - the operational decision (hard cut, or a
    crossfade of some duration using some named preset) a compositor
    then interprets. A custom plugin implements this exact same
    interface and registers under its own id; the Transition Engine
    never special-cases built-in vs. custom plugins, which is what makes
    this a real plugin architecture rather than an enum with a fixed
    set of cases."""

    plugin_id: str

    @abstractmethod
    def resolve(self, transition: Transition) -> TransitionRecipe: ...
