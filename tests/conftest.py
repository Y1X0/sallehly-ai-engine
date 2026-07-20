"""Shared test wiring for Phase 4 tests: builds a full, fully-offline
stack (LocalHeuristicLLMProvider + Wan21Adapter + LocalProvider) so
ProjectLifecycle/ProjectOrchestrator/apps.api can all be exercised
end-to-end with no network access, no API key, and no GPU.
"""

from __future__ import annotations

from dataclasses import dataclass

from ai_director import CreativeDirector
from asset_manager import AssetManager
from creative_compiler import CreativeCompiler
from director_memory import IDirectorMemoryStore, InMemoryDirectorMemoryStore
from llm_providers.local_heuristic_provider import LocalHeuristicLLMProvider
from persistence import InMemoryProjectStore, IProjectStore
from render_orchestrator import (
    GenerationPipeline,
    IGenerationJobStore,
    InMemoryEventBus,
    InMemoryGenerationJobStore,
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


def build_stack(
    compute_provider: IComputeProvider | None = None,
    engine: IVideoEngine | None = None,
) -> Stack:
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
    lifecycle = ProjectLifecycle(director, compiler, pipeline, project_store, memory, events)
    orchestrator = SyncProjectOrchestrator(lifecycle)

    return Stack(
        memory=memory,
        project_store=project_store,
        job_store=job_store,
        asset_manager=asset_manager,
        events=events,
        lifecycle=lifecycle,
        orchestrator=orchestrator,
    )


SAMPLE_BRIEF = dict(
    workspace_id="ws1",
    created_by="user1",
    prompt="A 12-second warm premium product ad for a minimalist watch",
    target_duration_sec=12,
    aspect_ratio="16:9",
)
