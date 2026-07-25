"""Standalone Temporal worker process - runs `ProjectGenerationWorkflow`/
`ProjectActivities` against a real Temporal server. Separate from
`apps/api`'s FastAPI process (production shape: an API replica only
starts/updates workflows, a worker process executes them) - see
docs/adr/0015-temporal-activation.md.

Run with:

    ORCHESTRATOR=temporal uv run python -m api.temporal_worker

Reuses `build_app_state()` - the same single source of truth
`apps/api`'s FastAPI process uses for which concrete
`ILLMProvider`/`IVideoEngine`/`IComputeProvider` are active - so the
worker and the API agree on configuration without duplicating any of
`state.py`'s wiring. `AppState.lifecycle` is what gets handed to
`ProjectActivities`; `AppState.orchestrator` (the `TemporalProjectOrchestrator`
built when `ORCHESTRATOR=temporal`) is unused here - a worker process
executes activities, it doesn't submit updates to itself.

Local-dev/this-environment caveat, documented rather than hidden: every
store `build_app_state()` wires today (`InMemoryProjectStore` et al,
Phase 8 WP2 has not landed yet) is in-process memory - running this
worker as a genuinely separate OS process from `apps/api` means the two
would NOT share project state, and every workflow update would hang
waiting for a project the worker's own `ProjectLifecycle` never saw.
Until WP2's Postgres-backed stores land, this only works if the worker
and the API share one process (see tests/test_temporal_orchestrator.py's
in-process background-thread pattern) - a real limitation of today's
persistence layer, not of the Temporal wiring itself.
"""

from __future__ import annotations

import asyncio
import logging

from config_sdk import get_settings
from render_orchestrator.workflows import build_worker
from temporalio.client import Client

from .state import build_app_state

logger = logging.getLogger(__name__)


async def main() -> None:
    settings = get_settings()
    app_state = build_app_state(settings)

    client = await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace)
    worker = build_worker(client, settings.temporal_task_queue, app_state.lifecycle)

    logger.info(
        "Temporal worker starting: address=%s namespace=%s task_queue=%s",
        settings.temporal_address,
        settings.temporal_namespace,
        settings.temporal_task_queue,
    )
    await worker.run()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
