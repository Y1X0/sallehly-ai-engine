"""Shared test wiring for Phase 4 tests: builds a full, fully-offline
stack (LocalHeuristicLLMProvider + Wan21Adapter + LocalProvider) so
ProjectLifecycle/ProjectOrchestrator/apps.api can all be exercised
end-to-end with no network access, no API key, and no GPU.
"""

from __future__ import annotations

from dataclasses import dataclass

from ai_director import CreativeDirector
from asset_manager import AssetManager
from auth import IAuthProvider, InMemoryUserStore, IUserStore, LocalAuthProvider
from cinematic_intelligence import CinematicIntelligenceCoordinator
from creative_compiler import CreativeCompiler
from director_memory import IDirectorMemoryStore, InMemoryDirectorMemoryStore
from llm_providers.local_heuristic_provider import LocalHeuristicLLMProvider
from persistence import InMemoryProjectStore, IProjectStore
from render_orchestrator import (
    GenerationPipeline,
    IGenerationJobStore,
    InMemoryEventBus,
    InMemoryGenerationJobStore,
    PostProductionRunner,
    ProjectLifecycle,
    SyncProjectOrchestrator,
)
from video_engine_adapter.adapters import Wan21Adapter
from video_engine_adapter.compute import LocalProvider
from video_engine_sdk import IComputeProvider, IVideoEngine


@dataclass
class Stack:
    memory: IDirectorMemoryStore
    project_store: IProjectStore
    job_store: IGenerationJobStore
    asset_manager: AssetManager
    events: InMemoryEventBus
    lifecycle: ProjectLifecycle
    orchestrator: SyncProjectOrchestrator
    user_store: IUserStore
    auth_provider: IAuthProvider
    cinematic_intelligence: CinematicIntelligenceCoordinator | None = None
    post_production: PostProductionRunner | None = None


def build_stack(
    compute_provider: IComputeProvider | None = None,
    engine: IVideoEngine | None = None,
    with_cinematic_intelligence: bool = False,
    with_post_production: bool = False,
) -> Stack:
    """`with_cinematic_intelligence`/`with_post_production` default False
    so every pre-Phase-8 test using this fixture is completely unaffected
    - only tests that explicitly opt in exercise the full Phase 8
    pipeline (see docs/adr/0014-pipeline-integration.md)."""
    memory = InMemoryDirectorMemoryStore()
    director = CreativeDirector(llm_provider=LocalHeuristicLLMProvider(), memory=memory)

    engine = engine or Wan21Adapter()
    compiler = CreativeCompiler(capability_manifest=engine.capabilities(), memory=memory)

    job_store = InMemoryGenerationJobStore()
    asset_manager = AssetManager()
    pipeline = GenerationPipeline(
        engine=engine,
        compute_provider=compute_provider or LocalProvider(),
        asset_manager=asset_manager,
        job_store=job_store,
    )

    project_store = InMemoryProjectStore()
    events = InMemoryEventBus()

    cinematic = CinematicIntelligenceCoordinator() if with_cinematic_intelligence else None
    post_production = PostProductionRunner(asset_manager) if with_post_production else None

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
    orchestrator = SyncProjectOrchestrator(lifecycle)

    user_store = InMemoryUserStore()
    auth_provider = LocalAuthProvider(user_store)

    return Stack(
        memory=memory,
        project_store=project_store,
        job_store=job_store,
        asset_manager=asset_manager,
        events=events,
        lifecycle=lifecycle,
        orchestrator=orchestrator,
        user_store=user_store,
        auth_provider=auth_provider,
        cinematic_intelligence=cinematic,
        post_production=post_production,
    )


SAMPLE_BRIEF = dict(
    workspace_id="ws1",
    created_by="user1",
    prompt="A 12-second warm premium product ad for a minimalist watch",
    target_duration_sec=12,
    aspect_ratio="16:9",
)

# apps/api's POST /projects derives workspace_id/created_by from the
# authenticated user's token rather than trusting the client - this is
# the request body shape for API-level tests (see test_api.py).
SAMPLE_PROJECT_REQUEST = dict(
    prompt="A 12-second warm premium product ad for a minimalist watch",
    target_duration_sec=12,
    aspect_ratio="16:9",
)
