from __future__ import annotations

from typing import Callable, Generic, TypeVar

T = TypeVar("T")


class Registry(Generic[T]):
    """Maps a config string (e.g. VIDEO_ENGINE=wan2.1) to a factory that
    builds the corresponding implementation. This is the mechanism every
    swap point in the system (LLM provider, video engine, compute
    provider) uses instead of if/elif chains scattered across services.
    """

    def __init__(self, name: str) -> None:
        self._name = name
        self._factories: dict[str, Callable[..., T]] = {}

    def register(self, key: str, factory: Callable[..., T]) -> None:
        if key in self._factories:
            raise ValueError(f"{self._name}: '{key}' is already registered")
        self._factories[key] = factory

    def register_if_absent(self, key: str, factory: Callable[..., T]) -> None:
        """Like register(), but a no-op if `key` is already registered.
        Used by module-level bootstrap functions (e.g.
        video_engine_adapter.register_defaults) that may be called more
        than once within a process (tests re-importing a module, ...)."""
        if key not in self._factories:
            self._factories[key] = factory

    def __contains__(self, key: str) -> bool:
        return key in self._factories

    def create(self, key: str, /, **kwargs: object) -> T:
        try:
            factory = self._factories[key]
        except KeyError as exc:
            available = ", ".join(sorted(self._factories)) or "(none registered)"
            raise KeyError(
                f"{self._name}: unknown key '{key}'. Available: {available}"
            ) from exc
        return factory(**kwargs)


# Populated at application startup by each concrete implementation module,
# e.g. `LLM_PROVIDER_REGISTRY.register("claude", ClaudeProvider)`.
LLM_PROVIDER_REGISTRY: Registry = Registry("LLM_PROVIDER")
VIDEO_ENGINE_REGISTRY: Registry = Registry("VIDEO_ENGINE")
COMPUTE_PROVIDER_REGISTRY: Registry = Registry("COMPUTE_PROVIDER")

# Keyed by Transition.type (or Transition.plugin_id for type="custom") ->
# an ITransitionPlugin factory. See services/post-processing/transitions
# for the built-ins and docs/adr/0012-post-production-pipeline.md for why
# this is a real plugin registry rather than an if/elif chain.
TRANSITION_PLUGIN_REGISTRY: Registry = Registry("TRANSITION_PLUGIN")

# Cinematic Intelligence Layer (Phase 7) plugin registries - see
# packages/cinematic-intelligence-sdk and
# docs/adr/0013-cinematic-intelligence-layer.md.

# Keyed by RepairAction.repair_type -> an IRepairStrategy factory. Built-ins
# in services/cinematic-intelligence/repair/.
REPAIR_STRATEGY_REGISTRY: Registry = Registry("REPAIR_STRATEGY")

# Keyed by engine_id ('wan2.1', 'veo', 'runway', 'luma', 'kling', 'pika', ...)
# -> an IPromptTranslator factory. Built-ins in
# services/cinematic-intelligence/prompt_intelligence/translators.py.
PROMPT_TRANSLATOR_REGISTRY: Registry = Registry("PROMPT_TRANSLATOR")

# Keyed by QualityReport.scores field name -> an IQualityMetric factory.
# Built-ins in services/cinematic-intelligence/quality_analyzer.py.
QUALITY_METRIC_REGISTRY: Registry = Registry("QUALITY_METRIC")

# Phase 8 model-adapter registries (docs/adr/0014-pipeline-integration.md).
# Both stay real, replaceable swap points even though every built-in
# adapter currently registered needs an optional ML dependency + model
# weights this sandbox doesn't have - see
# services/cinematic-intelligence/model_adapters/.

# Keyed by provider id ('clip', 'dino', ...) -> an IEmbeddingProvider factory.
EMBEDDING_PROVIDER_REGISTRY: Registry = Registry("EMBEDDING_PROVIDER")

# Keyed by adapter id ('controlnet', 'ip_adapter', ...) -> an
# IReferenceConditioningAdapter factory.
CONDITIONING_ADAPTER_REGISTRY: Registry = Registry("CONDITIONING_ADAPTER")
