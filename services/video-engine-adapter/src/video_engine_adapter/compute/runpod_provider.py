from __future__ import annotations

from video_engine_sdk import (
    ComputeJobHandle,
    ComputeJobStatus,
    EngineJobOutput,
    EngineJobPayload,
    IComputeProvider,
)

PROVIDER_ID = "runpod"


class RunPodProvider(IComputeProvider):
    """IComputeProvider backed by a RunPod Serverless Endpoint.

    Execution model: request/response. The endpoint is pre-deployed from
    the image built in workers/gpu-worker (see infra/runpod/), so submit()
    is just an HTTP POST to RunPod's /run, and get_status()/fetch_output()
    poll RunPod's /status/{id}. This is the cheapest way to get on-demand
    GPU access for early experiments with no infrastructure to manage
    (see docs/adr/0005-gpu-provider-runpod-vastai-first.md).
    """

    provider_id = PROVIDER_ID

    def __init__(self, api_key: str, endpoint_id: str) -> None:
        self._api_key = api_key
        self._endpoint_id = endpoint_id

    def submit(self, payload: EngineJobPayload) -> ComputeJobHandle:
        raise NotImplementedError(
            "Phase 3: POST payload.input to "
            "https://api.runpod.ai/v2/{endpoint_id}/run and wrap the "
            "returned RunPod job id in a ComputeJobHandle."
        )

    def get_status(self, handle: ComputeJobHandle) -> ComputeJobStatus:
        raise NotImplementedError(
            "Phase 3: GET /v2/{endpoint_id}/status/{handle.external_job_id} "
            "and map RunPod's IN_QUEUE/IN_PROGRESS/COMPLETED/FAILED to "
            "ComputeJobStatus."
        )

    def fetch_output(self, handle: ComputeJobHandle) -> EngineJobOutput:
        raise NotImplementedError(
            "Phase 3: read the completed status response's `output` field "
            "(expected to contain a storage URI the worker uploaded to) "
            "and wrap it in an EngineJobOutput."
        )

    def cancel(self, handle: ComputeJobHandle) -> None:
        raise NotImplementedError(
            "Phase 3: POST /v2/{endpoint_id}/cancel/{handle.external_job_id}."
        )
