"""Tests for RunPodProvider against a mocked RunPod Serverless HTTP API
(httpx.MockTransport - no real network access, no API key). Covers the
happy path, transient-error retry, and fail-fast-on-4xx behavior asked
for by Phase 3's "mocked GPU job tests" / "failure/retry tests".
"""

from __future__ import annotations

import httpx
import pytest
from video_engine_adapter.compute.runpod_provider import RunPodComputeError, RunPodProvider
from video_engine_sdk import ComputeJobStatus, EngineJobPayload
from video_engine_sdk.types import ComputeResourceRequirements

SAMPLE_PAYLOAD = EngineJobPayload(
    container_image="sallehly/wan21-worker:2.1.0",
    input={"prompt": "a watch on marble"},
    resources=ComputeResourceRequirements(min_vram_gb=24.0),
)


def _provider(handler, **kwargs) -> RunPodProvider:
    client = httpx.Client(
        base_url="https://api.runpod.ai/v2/test-endpoint",
        transport=httpx.MockTransport(handler),
    )
    return RunPodProvider(api_key="fake-key", endpoint_id="test-endpoint", client=client, **kwargs)


def test_submit_returns_compute_job_handle():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v2/test-endpoint/run"
        return httpx.Response(200, json={"id": "job-123", "status": "IN_QUEUE"})

    provider = _provider(handler)
    handle = provider.submit(SAMPLE_PAYLOAD)

    assert handle.provider_id == "runpod"
    assert handle.external_job_id == "job-123"


def test_get_status_maps_runpod_statuses():
    responses = iter(["IN_QUEUE", "IN_PROGRESS", "COMPLETED", "FAILED", "CANCELLED"])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": "job-123", "status": next(responses)})

    from video_engine_sdk import ComputeJobHandle

    provider = _provider(handler)
    handle = ComputeJobHandle(provider_id="runpod", external_job_id="job-123")

    assert provider.get_status(handle) == ComputeJobStatus.QUEUED
    assert provider.get_status(handle) == ComputeJobStatus.RUNNING
    assert provider.get_status(handle) == ComputeJobStatus.SUCCEEDED
    assert provider.get_status(handle) == ComputeJobStatus.FAILED
    assert provider.get_status(handle) == ComputeJobStatus.CANCELLED


def test_fetch_output_returns_engine_job_output_on_success():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "job-123",
                "status": "COMPLETED",
                "output": {"output_uri": "s3://bucket/clip.mp4", "engine_metadata": {"frames": 72}},
            },
        )

    from video_engine_sdk import ComputeJobHandle

    provider = _provider(handler)
    handle = ComputeJobHandle(provider_id="runpod", external_job_id="job-123")

    output = provider.fetch_output(handle)

    assert output.output_uri == "s3://bucket/clip.mp4"
    assert output.engine_metadata == {"frames": 72}


def test_fetch_output_raises_if_job_not_yet_succeeded():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": "job-123", "status": "IN_PROGRESS"})

    from video_engine_sdk import ComputeJobHandle

    provider = _provider(handler)
    handle = ComputeJobHandle(provider_id="runpod", external_job_id="job-123")

    with pytest.raises(RunPodComputeError, match="before job succeeded"):
        provider.fetch_output(handle)


def test_fetch_output_raises_on_missing_output_uri():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": "job-123", "status": "COMPLETED", "output": {}})

    from video_engine_sdk import ComputeJobHandle

    provider = _provider(handler)
    handle = ComputeJobHandle(provider_id="runpod", external_job_id="job-123")

    with pytest.raises(RunPodComputeError, match="output_uri"):
        provider.fetch_output(handle)


def test_transient_5xx_is_retried_then_succeeds():
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        if call_count["n"] < 3:
            return httpx.Response(500, text="internal error")
        return httpx.Response(200, json={"id": "job-123", "status": "IN_QUEUE"})

    provider = _provider(handler, max_attempts=3, retry_backoff_sec=0.0)
    handle = provider.submit(SAMPLE_PAYLOAD)

    assert handle.external_job_id == "job-123"
    assert call_count["n"] == 3


def test_5xx_exhausting_retries_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="still down")

    provider = _provider(handler, max_attempts=2, retry_backoff_sec=0.0)

    with pytest.raises(RunPodComputeError, match="503"):
        provider.submit(SAMPLE_PAYLOAD)


def test_4xx_fails_immediately_without_retry():
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(401, text="unauthorized")

    provider = _provider(handler, max_attempts=5, retry_backoff_sec=0.0)

    with pytest.raises(RunPodComputeError, match="401"):
        provider.submit(SAMPLE_PAYLOAD)

    assert call_count["n"] == 1


def test_unrecognized_status_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": "job-123", "status": "SOMETHING_NEW"})

    from video_engine_sdk import ComputeJobHandle

    provider = _provider(handler)
    handle = ComputeJobHandle(provider_id="runpod", external_job_id="job-123")

    with pytest.raises(RunPodComputeError, match="Unrecognized"):
        provider.get_status(handle)
