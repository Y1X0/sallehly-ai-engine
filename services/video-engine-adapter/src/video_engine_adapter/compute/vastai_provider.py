from __future__ import annotations

from video_engine_sdk import (
    ComputeJobHandle,
    ComputeJobStatus,
    EngineJobOutput,
    EngineJobPayload,
    IComputeProvider,
)

PROVIDER_ID = "vastai"


class VastAIProvider(IComputeProvider):
    """IComputeProvider backed by a rented Vast.ai on-demand GPU instance.

    Execution model differs from RunPod: Vast.ai rents a raw instance,
    it does not offer a managed request/response serverless API. To keep
    the same IComputeProvider contract, the rented instance runs the same
    workers/gpu-worker image but with a thin, self-hosted queue-consumer
    HTTP server (infra/runpod's sibling: infra/vastai/) exposing an
    equivalent /submit, /status/{id}, /output/{id} surface. From this
    class's perspective (and everything above it) the two providers look
    identical - only the base URL and auth differ.
    """

    provider_id = PROVIDER_ID

    def __init__(self, instance_host: str, api_key: str) -> None:
        self._instance_host = instance_host
        self._api_key = api_key

    def submit(self, payload: EngineJobPayload) -> ComputeJobHandle:
        raise NotImplementedError(
            "Phase 3: POST payload.input to "
            "http://{instance_host}/submit on the self-hosted job runner."
        )

    def get_status(self, handle: ComputeJobHandle) -> ComputeJobStatus:
        raise NotImplementedError(
            "Phase 3: GET http://{instance_host}/status/{handle.external_job_id}."
        )

    def fetch_output(self, handle: ComputeJobHandle) -> EngineJobOutput:
        raise NotImplementedError(
            "Phase 3: GET http://{instance_host}/output/{handle.external_job_id}, "
            "expected to return a URI into shared object storage (the "
            "instance uploads directly to the configured S3/R2 bucket)."
        )

    def cancel(self, handle: ComputeJobHandle) -> None:
        raise NotImplementedError(
            "Phase 3: POST http://{instance_host}/cancel/{handle.external_job_id}."
        )
