"""LocalProvider (services/video-engine-adapter, dev/test IComputeProvider):
regression coverage for its output directory being removed out from under a
long-running process (found via the Phase 5 frontend e2e suite - a
`.docker-data` cleanup between manual verification runs left a stale
`LocalProvider` instance whose `submit()` then failed with FileNotFoundError,
since the directory was only created once in `__init__`).
"""

from __future__ import annotations

import shutil

from video_engine_adapter.compute import LocalProvider
from video_engine_sdk import ComputeJobStatus, ComputeResourceRequirements, EngineJobPayload


def test_submit_recreates_output_dir_if_removed_after_construction(tmp_path):
    output_dir = tmp_path / "local-render-output"
    provider = LocalProvider(output_dir=str(output_dir))
    assert output_dir.exists()

    shutil.rmtree(output_dir)
    assert not output_dir.exists()

    payload = EngineJobPayload(
        container_image="wan2.1:latest",
        input={"prompt": "a test shot"},
        resources=ComputeResourceRequirements(min_vram_gb=16),
    )
    handle = provider.submit(payload)

    assert output_dir.exists()
    assert provider.get_status(handle) == ComputeJobStatus.SUCCEEDED
