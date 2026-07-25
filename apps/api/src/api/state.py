from __future__ import annotations

from dataclasses import dataclass

from ai_director import CreativeDirector
from asset_manager import AssetManager
from auth import IAuthProvider, IUserStore, InMemoryUserStore, LocalAuthProvider
from cinematic_intelligence import CinematicIntelligenceCoordinator
from cinematic_intelligence.model_adapters import register_defaults as register_model_adapters
from config_sdk import VIDEO_ENGINE_REGISTRY, Settings
from creative_compiler import CreativeCompiler
from director_memory import IDirectorMemoryStore, InMemoryDirectorMemoryStore
from llm_providers import ILLMProvider
from llm_providers.local_heuristic_provider import LocalHeuristicLLMProvider
from persistence import IProjectStore, InMemoryProjectStore
from render_orchestrator import (
    GenerationPipeline,
    IGenerationJobStore,
    InMemoryEventBus,
    InMemoryGenerationJobStore,
    IProjectOrchestrator,
    PostProductionRunner,
    ProjectLifecycle,
    SyncProjectOrchestrator,
)
from storage_sdk import IStorageProvider, LocalFilesystemStorageProvider
from video_engine_adapter import register_defaults as register_engine_defaults
from video_engine_adapter.compute import LocalProvider
from video_engine_sdk import IComputeProvider, IVideoEngine


@dataclass
class AppState:
    project_store: IProjectStore
    job_store: IGenerationJobStore
    asset_manager: AssetManager
    orchestrator: IProjectOrchestrator
    user_store: IUserStore
    auth_provider: IAuthProvider
    memory: IDirectorMemoryStore
    cinematic_intelligence: CinematicIntelligenceCoordinator


def build_app_state(settings: Settings) -> AppState:
    """Wires every interface to a concrete default for this environment:
    `LocalHeuristicLLMProvider` (no API key required) and `Wan21Adapter`
    + `LocalProvider` (no GPU required) - see docs/DEV_SETUP.md.

    Swapping to `ClaudeProvider`/`RunPodProvider` is a config change
    (`LLM_PROVIDER=claude` + `ANTHROPIC_API_KEY=...`,
    `COMPUTE_PROVIDER=runpod` + `RUNPOD_API_KEY=...`), not a code change.
    Swapping the video engine (`VIDEO_ENGINE=wan2.1` / `sallehly-v1` /
    any future `IVideoEngine`) goes through the same
    `VIDEO_ENGINE_REGISTRY` config_sdk registry every other provider
    registry uses (ADR 0014) - `register_engine_defaults()` populates it
    with every engine `services/video-engine-adapter` ships.
    This function is the *one place* that reads those config values and
    picks a concrete implementation - every service above it
    (CreativeDirector, CreativeCompiler, GenerationPipeline,
    ProjectLifecycle) only ever sees the interfaces.
    """
    register_engine_defaults()
    register_model_adapters()
    memory: IDirectorMemoryStore = InMemoryDirectorMemoryStore()

    llm: ILLMProvider
    if settings.llm_provider == "claude" and settings.anthropic_api_key:
        from llm_providers.claude_provider import ClaudeProvider

        llm = ClaudeProvider(api_key=settings.anthropic_api_key)
    else:
        llm = LocalHeuristicLLMProvider()

    director = CreativeDirector(llm_provider=llm, memory=memory)

    engine: IVideoEngine = VIDEO_ENGINE_REGISTRY.create(settings.video_engine)
    compiler = CreativeCompiler(capability_manifest=engine.capabilities(), memory=memory)

    compute: IComputeProvider
    if settings.compute_provider == "runpod" and settings.runpod_api_key:
        from video_engine_adapter.compute import RunPodProvider

        compute = RunPodProvider(api_key=settings.runpod_api_key, endpoint_id=settings.runpod_endpoint_id)
    else:
        compute = LocalProvider()

    storage: IStorageProvider = LocalFilesystemStorageProvider()
    job_store: IGenerationJobStore = InMemoryGenerationJobStore()
    asset_manager = AssetManager(storage=storage)
    pipeline = GenerationPipeline(
        engine=engine, compute_provider=compute, asset_manager=asset_manager, job_store=job_store
    )

    project_store: IProjectStore = InMemoryProjectStore()
    events = InMemoryEventBus()
    cinematic = CinematicIntelligenceCoordinator()
    post_production = PostProductionRunner(asset_manager)
    lifecycle = ProjectLifecycle(
        director,
        compiler,
        pipeline,
        project_store,
        memory,
        events,
        cinematic_intelligence=cinematic,
        post_production=post_production,
    )
    orchestrator: IProjectOrchestrator = SyncProjectOrchestrator(lifecycle)

    user_store: IUserStore = InMemoryUserStore()
    auth_provider: IAuthProvider = LocalAuthProvider(user_store)

    return AppState(
        project_store=project_store,
        job_store=job_store,
        asset_manager=asset_manager,
        orchestrator=orchestrator,
        user_store=user_store,
        auth_provider=auth_provider,
        memory=memory,
        cinematic_intelligence=cinematic,
    )
