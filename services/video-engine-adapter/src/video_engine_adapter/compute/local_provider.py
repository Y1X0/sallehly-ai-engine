from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from video_engine_sdk import (
    ComputeJobHandle,
    ComputeJobStatus,
    EngineJobOutput,
    EngineJobPayload,
    IComputeProvider,
)

PROVIDER_ID = "local"


class LocalProvider(IComputeProvider):
    """No-GPU, no-network IComputeProvider for local development.

    Writes the payload it "would have" sent to a real engine as a JSON
    stub file and immediately reports success. This lets the entire
    pipeline (AI Director -> ... -> Render Orchestrator -> Post-Processing)
    be exercised end-to-end on a laptop with COMPUTE_PROVIDER=local,
    without a GPU, an API key, or rented compute of any kind. It is never
    used in staging/production.
    """

    provider_id = PROVIDER_ID

    def __init__(self, output_dir: str = "./.docker-data/local-render-output") -> None:
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def submit(self, payload: EngineJobPayload) -> ComputeJobHandle:
        # Re-create defensively: __init__'s mkdir only runs once at process
        # startup, but this directory is ephemeral local-dev scratch space
        # that can be cleared out from under a long-running process (e.g.
        # a cleanup script, container volume reset) - a submit() shouldn't
        # permanently fail just because that happened once.
        self._output_dir.mkdir(parents=True, exist_ok=True)
        job_id = str(uuid.uuid4())
        stub_path = self._output_dir / f"{job_id}.json"
        stub_path.write_text(
            json.dumps(
                {
                    "container_image": payload.container_image,
                    "input": payload.input,
                    "submitted_at": time.time(),
                    "note": "LocalProvider stub output - not a real render.",
                },
                indent=2,
            )
        )
        return ComputeJobHandle(provider_id=self.provider_id, external_job_id=job_id)

    def get_status(self, handle: ComputeJobHandle) -> ComputeJobStatus:
        stub_path = self._output_dir / f"{handle.external_job_id}.json"
        return ComputeJobStatus.SUCCEEDED if stub_path.exists() else ComputeJobStatus.FAILED

    def fetch_output(self, handle: ComputeJobHandle) -> EngineJobOutput:
        stub_path = self._output_dir / f"{handle.external_job_id}.json"
        return EngineJobOutput(
            output_uri=f"file://{stub_path.resolve()}",
            engine_metadata={"provider": self.provider_id, "mock": True},
        )

    def cancel(self, handle: ComputeJobHandle) -> None:
        stub_path = self._output_dir / f"{handle.external_job_id}.json"
        stub_path.unlink(missing_ok=True)
