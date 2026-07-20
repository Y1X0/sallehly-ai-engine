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
