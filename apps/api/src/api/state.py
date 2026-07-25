from __future__ import annotations

from dataclasses import asdict, dataclass

from ai_director import CreativeDirector
from asset_manager import AssetManager
from auth import IAuthProvider, ITokenStore, IUserStore, InMemoryTokenStore, InMemoryUserStore, LocalAuthProvider
from cache_sdk import ICache, InMemoryCache
from cinematic_intelligence import CinematicIntelligenceCoordinator
from cinematic_intelligence.model_adapters import register_defaults as register_model_adapters
from config_sdk import VIDEO_ENGINE_REGISTRY, Settings
from creative_compiler import CreativeCompiler
from director_memory import IDirectorMemoryStore, InMemoryDirectorMemoryStore
from llm_providers import ILLMProvider
from llm_providers.local_heuristic_provider import LocalHeuristicLLMProvider
from observability import IErrorReporter, LoggingErrorReporter
from persistence import IProjectStore, InMemoryProjectStore
from render_orchestrator import (
    GenerationPipeline,
    IEventBus,
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
from video_engine_sdk import CapabilityManifest, IComputeProvider, IVideoEngine


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
    error_reporter: IErrorReporter
    lifecycle: ProjectLifecycle
    """Exposed separately from `orchestrator` (Phase 8 WP6, ADR 0015) so
    `apps/api/src/api/temporal_worker.py` - a standalone process, not a
    route handler - can host the exact same `ProjectLifecycle` a
    Temporal worker's `ProjectActivities` needs, reusing this one
    function as the single source of truth for how every concrete
    provider is wired, whether the API or the worker process reads it."""


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

    cache: ICache
    if settings.cache_backend == "redis":
        # Lazy import: keeps `redis` off the hot path for every
        # environment that never selects it - same discipline as every
        # other lazy import in this function. See
        # docs/adr/0017-redis-backed-infra.md.
        from cache_sdk import RedisCache

        cache = RedisCache(settings.redis_url)
    else:
        cache = InMemoryCache()

    engine: IVideoEngine = VIDEO_ENGINE_REGISTRY.create(settings.video_engine)
    capability_manifest = _get_cached_capability_manifest(cache, engine, settings.video_engine)
    compiler = CreativeCompiler(capability_manifest=capability_manifest, memory=memory)

    compute: IComputeProvider
    if settings.compute_provider == "runpod" and settings.runpod_api_key:
        from video_engine_adapter.compute import RunPodProvider

        compute = RunPodProvider(api_key=settings.runpod_api_key, endpoint_id=settings.runpod_endpoint_id)
    else:
        compute = LocalProvider()

    storage: IStorageProvider
    if settings.storage_provider == "s3":
        # Lazy import: keeps `boto3` off the hot path for every
        # environment that never selects it - same discipline as every
        # other lazy import in this function. See
        # docs/adr/0018-s3-storage-provider.md.
        from storage_sdk import S3Provider

        storage = S3Provider(
            settings.storage_bucket,
            endpoint_url=settings.storage_endpoint_url or None,
            access_key=settings.storage_access_key or None,
            secret_key=settings.storage_secret_key or None,
        )
    else:
        storage = LocalFilesystemStorageProvider()
    job_store: IGenerationJobStore = InMemoryGenerationJobStore()
    asset_manager = AssetManager(storage=storage)
    pipeline = GenerationPipeline(
        engine=engine, compute_provider=compute, asset_manager=asset_manager, job_store=job_store
    )

    project_store: IProjectStore
    if settings.project_store == "postgres":
        # Lazy import: keeps `sqlalchemy`/`psycopg` off the hot path for
        # every environment that never selects it - same discipline as
        # the temporal client import below. See
        # docs/adr/0016-postgres-persistence.md.
        from persistence import PostgresProjectStore

        project_store = PostgresProjectStore(settings.database_url)
    else:
        project_store = InMemoryProjectStore()

    events: IEventBus
    if settings.event_bus == "redis":
        # Lazy import: keeps `redis` off the hot path for every
        # environment that never selects it. See
        # docs/adr/0017-redis-backed-infra.md.
        from render_orchestrator.redis_event_bus import RedisEventBus

        events = RedisEventBus(settings.redis_url)
    else:
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
    orchestrator: IProjectOrchestrator
    if settings.orchestrator == "temporal":
        # Lazy import: keeps `temporalio` off the hot path for every
        # environment that never selects it (the "sync" default every
        # pre-Phase-8 deployment and this environment's own tests still
        # use) - same discipline as ClaudeProvider/RunPodProvider's own
        # lazy imports above. See docs/adr/0015-temporal-activation.md.
        import asyncio

        from temporalio.client import Client

        from render_orchestrator.workflows import TemporalProjectOrchestrator

        client = asyncio.run(Client.connect(settings.temporal_address, namespace=settings.temporal_namespace))
        orchestrator = TemporalProjectOrchestrator(client, settings.temporal_task_queue)
    else:
        orchestrator = SyncProjectOrchestrator(lifecycle)

    user_store: IUserStore = InMemoryUserStore()
    token_store: ITokenStore
    if settings.token_store == "redis":
        # Lazy import: keeps `redis` off the hot path for every
        # environment that never selects it. See
        # docs/adr/0017-redis-backed-infra.md.
        from auth import RedisTokenStore

        token_store = RedisTokenStore(settings.redis_url)
    else:
        token_store = InMemoryTokenStore()
    auth_provider: IAuthProvider = LocalAuthProvider(user_store, token_store=token_store)

    error_reporter: IErrorReporter
    if settings.error_reporter == "sentry" and settings.sentry_dsn:
        # Lazy import: keeps `sentry-sdk` off the hot path for every
        # environment that never selects it - same discipline as every
        # other lazy import in this function. See
        # docs/adr/0019-observability.md.
        from observability import SentryErrorReporter

        error_reporter = SentryErrorReporter(settings.sentry_dsn)
    else:
        error_reporter = LoggingErrorReporter()

    return AppState(
        project_store=project_store,
        job_store=job_store,
        asset_manager=asset_manager,
        orchestrator=orchestrator,
        user_store=user_store,
        auth_provider=auth_provider,
        memory=memory,
        cinematic_intelligence=cinematic,
        error_reporter=error_reporter,
        lifecycle=lifecycle,
    )


def _get_cached_capability_manifest(cache: ICache, engine: IVideoEngine, video_engine: str) -> CapabilityManifest:
    """Real `ICache` consumer proving the Phase 8 WP3 plumbing works
    (`docs/adr/0017-redis-backed-infra.md`) - `engine.capabilities()` is
    the first of `docs/PHASE8_SCALEOUT_PLAN.md`'s three candidate cache
    targets (capability-manifest lookups, prompt-template renders,
    project-list pagination), chosen as the lowest-risk one to
    demonstrate the mechanism against a real Redis server: it's pure,
    JSON-shaped data keyed by `video_engine`, with no correctness risk if
    a cached value briefly outlives an engine registry change (the
    `ttl_seconds=3600` bound already handles that)."""
    cache_key = f"capability_manifest:{video_engine}"
    cached = cache.get(cache_key)
    if cached is not None:
        cached = dict(cached)
        cached["motion_strength_range"] = tuple(cached["motion_strength_range"])
        return CapabilityManifest(**cached)

    manifest = engine.capabilities()
    cache.set(cache_key, asdict(manifest), ttl_seconds=3600)
    return manifest
