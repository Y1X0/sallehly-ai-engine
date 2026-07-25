from .camera_continuity import CameraContinuityEngine, CameraContinuityEngineError
from .character_consistency import CharacterConsistencyEngine, CharacterConsistencyEngineError
from .coordinator import CinematicIntelligenceCoordinator, CinematicIntelligenceCoordinatorError
from .environment_consistency import EnvironmentConsistencyEngine, EnvironmentConsistencyEngineError
from .memory_graph import DirectorMemoryGraph, DirectorMemoryGraphError, InMemoryGraphStore
from .model_adapters import (
    ClipEmbeddingProvider,
    ControlNetConditioningAdapter,
    DinoEmbeddingProvider,
    IPAdapterConditioningAdapter,
    ModelUnavailableError,
)
from .model_adapters import register_defaults as _register_model_adapters
from .object_consistency import ObjectConsistencyEngine, ObjectConsistencyEngineError
from .prompt_intelligence import PromptIntelligenceEngine
from .prompt_intelligence import register_defaults as _register_prompt_translators
from .quality_analyzer import SceneQualityAnalyzer, SceneQualityAnalyzerError
from .quality_analyzer import register_defaults as _register_quality_metrics
from .reference_images import ReferenceImageEngine, ReferenceImageEngineError
from .repair import AutomaticRepairEngine, AutomaticRepairEngineError
from .repair import register_defaults as _register_repair_strategies
from .scene_continuity import SceneContinuityEngine, SceneContinuityEngineError
from .style_lock import StyleLockEngine, StyleLockEngineError
from .temporal_memory import TemporalMemoryEngine, TemporalMemoryEngineError


def register_defaults() -> None:
    """Registers every Cinematic Intelligence Layer built-in plugin
    (prompt translators, quality metrics, repair strategies) into their
    respective config_sdk registries. Idempotent - call once at process
    startup (or freely again in tests), same convention as
    post_processing.register_defaults()."""
    _register_prompt_translators()
    _register_quality_metrics()
    _register_repair_strategies()
    _register_model_adapters()


__all__ = [
    "AutomaticRepairEngine",
    "AutomaticRepairEngineError",
    "CameraContinuityEngine",
    "CameraContinuityEngineError",
    "CharacterConsistencyEngine",
    "CharacterConsistencyEngineError",
    "CinematicIntelligenceCoordinator",
    "CinematicIntelligenceCoordinatorError",
    "ClipEmbeddingProvider",
    "ControlNetConditioningAdapter",
    "DinoEmbeddingProvider",
    "DirectorMemoryGraph",
    "DirectorMemoryGraphError",
    "EnvironmentConsistencyEngine",
    "EnvironmentConsistencyEngineError",
    "InMemoryGraphStore",
    "IPAdapterConditioningAdapter",
    "ModelUnavailableError",
    "ObjectConsistencyEngine",
    "ObjectConsistencyEngineError",
    "PromptIntelligenceEngine",
    "ReferenceImageEngine",
    "ReferenceImageEngineError",
    "SceneContinuityEngine",
    "SceneContinuityEngineError",
    "SceneQualityAnalyzer",
    "SceneQualityAnalyzerError",
    "StyleLockEngine",
    "StyleLockEngineError",
    "TemporalMemoryEngine",
    "TemporalMemoryEngineError",
    "register_defaults",
]
