from __future__ import annotations

from abc import ABC, abstractmethod

from .types import PromptPackage


class IPromptTranslator(ABC):
    """One entry in the Prompt Intelligence Engine's plugin registry
    (config_sdk.registry.PROMPT_TRANSLATOR_REGISTRY, key = engine_id -
    'wan2.1', 'veo', 'runway', 'luma', 'kling', 'pika', a future Sallehly
    model, ...). Translates an engine-agnostic PromptPackage into that
    engine's preferred prompt phrasing/keyword vocabulary, returning a
    new PromptPackage with `engine_id`/`translated_prompt` set - it never
    mutates `positive_prompt`/`negative_prompt`, which remain the
    engine-agnostic source of truth. Adding a new engine means adding a
    new IPromptTranslator, never branching inside PromptOptimizer."""

    engine_id: str

    @abstractmethod
    def translate(self, package: PromptPackage) -> PromptPackage: ...
