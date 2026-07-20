from __future__ import annotations

import time

import httpx

from video_engine_sdk import (
    ComputeJobHandle,
    ComputeJobStatus,
    EngineJobOutput,
    EngineJobPayload,
    IComputeProvider,
)

PROVIDER_ID = "runpod"
_BASE_URL = "https://api.runpod.ai/v2"

_STATUS_MAP: dict[str, ComputeJobStatus] = {
    "IN_QUEUE": ComputeJobStatus.QUEUED,
    "IN_PROGRESS": ComputeJobStatus.RUNNING,
    "COMPLETED": ComputeJobStatus.SUCCEEDED,
    "FAILED": ComputeJobStatus.FAILED,
    "CANCELLED": ComputeJobStatus.CANCELLED,
    "TIMED_OUT": ComputeJobStatus.FAILED,
}


class RunPodComputeError(Exception):
    """Raised on any RunPod API failure: transport error, non-2xx
    response (after retries are exhausted), or an unrecognized status
    string. Always carries a human-readable message - this is the
    "failure reporting" surface GenerationPipeline records onto a
    GenerationJob's error_message."""


class RunPodProvider(IComputeProvider):
    """IComputeProvider backed by a RunPod Serverless Endpoint.

    Execution model: request/response. The endpoint is pre-deployed from
    the image built in workers/gpu-worker (see infra/runpod/), so submit()
    is just an HTTP POST to RunPod's /run, and get_status()/fetch_output()
    poll RunPod's /status/{id}. This is the cheapest way to get on-demand
    GPU access for early experiments with no infrastructure to manage
    (see docs/adr/0005-gpu-provider-runpod-vastai-first.md).

    Transient failures (connection errors, 5xx responses) are retried
    with a short backoff; 4xx responses (bad request, bad auth) fail
    immediately since retrying won't change the outcome.
    """

    provider_id = PROVIDER_ID

    def __init__(
        self,
        api_key: str,
        endpoint_id: str,
        *,
        timeout_sec: float = 30.0,
        max_attempts: int = 3,
        retry_backoff_sec: float = 0.5,
        client: httpx.Client | None = None,
    ) -> None:
        self._endpoint_id = endpoint_id
        self._max_attempts = max_attempts
        self._retry_backoff_sec = retry_backoff_sec
        self._client = client or httpx.Client(
            base_url=f"{_BASE_URL}/{endpoint_id}",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout_sec,
        )

    def submit(self, payload: EngineJobPayload) -> ComputeJobHandle:
        response = self._request("POST", "/run", json={"input": payload.input})
        job_id = response.get("id")
        if not job_id:
            raise RunPodComputeError(f"RunPod /run response missing job id: {response}")
        return ComputeJobHandle(provider_id=self.provider_id, external_job_id=job_id)

    def get_status(self, handle: ComputeJobHandle) -> ComputeJobStatus:
        response = self._request("GET", f"/status/{handle.external_job_id}")
        return self._map_status(response)

    def fetch_output(self, handle: ComputeJobHandle) -> EngineJobOutput:
        response = self._request("GET", f"/status/{handle.external_job_id}")
        status = self._map_status(response)
        if status != ComputeJobStatus.SUCCEEDED:
            raise RunPodComputeError(
                f"fetch_output called before job succeeded (status={status.value}); "
                f"RunPod error field: {response.get('error')!r}"
            )

        output = response.get("output") or {}
        output_uri = output.get("output_uri")
        if not output_uri:
            raise RunPodComputeError(
                f"RunPod job {handle.external_job_id} completed but its output is missing "
                f"'output_uri' (see workers/gpu-worker/handler.py's expected return shape): {output}"
            )
        return EngineJobOutput(
            output_uri=output_uri,
            engine_metadata=output.get("engine_metadata", {}),
        )

    def cancel(self, handle: ComputeJobHandle) -> None:
        self._request("POST", f"/cancel/{handle.external_job_id}")

    def _request(self, method: str, path: str, **kwargs: object) -> dict:
        last_error: RunPodComputeError | None = None

        for attempt in range(self._max_attempts):
            try:
                response = self._client.request(method, path, **kwargs)
            except httpx.HTTPError as exc:
                last_error = RunPodComputeError(
                    f"RunPod API transport error for {method} {path} (attempt {attempt + 1}/"
                    f"{self._max_attempts}): {exc}"
                )
                self._sleep_before_retry(attempt)
                continue

            if response.status_code >= 500:
                last_error = RunPodComputeError(
                    f"RunPod API returned {response.status_code} for {method} {path} "
                    f"(attempt {attempt + 1}/{self._max_attempts}): {response.text}"
                )
                self._sleep_before_retry(attempt)
                continue

            if response.status_code >= 400:
                # Client error (bad request, bad auth, unknown job id, ...) - retrying
                # with the same request will not help, fail immediately.
                raise RunPodComputeError(
                    f"RunPod API returned {response.status_code} for {method} {path}: {response.text}"
                )

            return response.json()

        assert last_error is not None
        raise last_error

    def _sleep_before_retry(self, attempt: int) -> None:
        if attempt < self._max_attempts - 1:
            time.sleep(self._retry_backoff_sec * (attempt + 1))

    @staticmethod
    def _map_status(response: dict) -> ComputeJobStatus:
        raw_status = response.get("status", "")
        try:
            return _STATUS_MAP[raw_status]
        except KeyError:
            raise RunPodComputeError(f"Unrecognized RunPod status: {raw_status!r}") from None
