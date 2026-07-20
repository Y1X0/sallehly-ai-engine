"""End-to-end API contract tests: real HTTP requests via
fastapi.testclient.TestClient (no live server, no network) against the
actual apps/api routes, wired to the fully offline default stack
(LocalHeuristicLLMProvider + Wan21Adapter + LocalProvider).
"""

from __future__ import annotations

from api.dependencies import get_app_state
from api.main import app
from api.state import AppState
from conftest import SAMPLE_BRIEF, build_stack
from fastapi.testclient import TestClient
from video_engine_sdk import ComputeJobHandle, ComputeJobStatus, EngineJobOutput, EngineJobPayload, IComputeProvider


def _client() -> TestClient:
    return TestClient(app)


def _create_project(client: TestClient) -> dict:
    response = client.post("/projects", json=SAMPLE_BRIEF)
    assert response.status_code == 201
    return response.json()


def test_create_and_get_project():
    with _client() as client:
        project = _create_project(client)
        assert project["status"] == "created"

        response = client.get(f"/projects/{project['project_id']}")
        assert response.status_code == 200
        assert response.json()["project_id"] == project["project_id"]


def test_get_missing_project_returns_404():
    with _client() as client:
        response = client.get("/projects/does-not-exist")
        assert response.status_code == 404


def test_approve_storyboard_before_plan_returns_409():
    with _client() as client:
        project = _create_project(client)
        response = client.post(f"/projects/{project['project_id']}/approve-storyboard")
        assert response.status_code == 409


def test_full_lifecycle_over_http_reaches_completed_with_assets_and_jobs():
    with _client() as client:
        project = _create_project(client)
        project_id = project["project_id"]

        response = client.post(f"/projects/{project_id}/generate-plan")
        assert response.status_code == 200
        assert response.json()["status"] == "waiting_storyboard_approval"

        response = client.post(f"/projects/{project_id}/approve-storyboard")
        assert response.status_code == 200
        assert response.json()["status"] == "waiting_render_approval"

        response = client.post(f"/projects/{project_id}/approve-render")
        assert response.status_code == 200
        assert response.json()["status"] == "approved"

        response = client.post(f"/projects/{project_id}/generate-video")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "completed"
        job_ids = body["generation_job_ids"]
        asset_ids = body["asset_ids"]
        assert len(job_ids) > 0
        assert len(asset_ids) == len(job_ids)

        response = client.get(f"/jobs/{job_ids[0]}")
        assert response.status_code == 200
        assert response.json()["status"] == "completed"

        response = client.get(f"/jobs/{job_ids[0]}/status")
        assert response.status_code == 200
        assert response.json() == {
            "job_id": job_ids[0],
            "status": "completed",
            "retry_count": 0,
            "error_message": None,
        }

        response = client.get(f"/projects/{project_id}/assets")
        assert response.status_code == 200
        assets_body = response.json()
        assert assets_body["project_id"] == project_id
        assert len(assets_body["assets"]) == len(asset_ids)


def test_get_missing_job_returns_404():
    with _client() as client:
        response = client.get("/jobs/does-not-exist")
        assert response.status_code == 404
        response = client.get("/jobs/does-not-exist/status")
        assert response.status_code == 404


def test_reject_storyboard_over_http_regenerates_and_stays_at_gate_one():
    with _client() as client:
        project = _create_project(client)
        project_id = project["project_id"]
        client.post(f"/projects/{project_id}/generate-plan")

        response = client.post(
            f"/projects/{project_id}/reject-storyboard", json={"feedback": ["too static"]}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "waiting_storyboard_approval"
        assert body["rejected_stage"] is None


def test_reject_render_over_http_with_quality_tier_override():
    with _client() as client:
        project = _create_project(client)
        project_id = project["project_id"]
        client.post(f"/projects/{project_id}/generate-plan")
        client.post(f"/projects/{project_id}/approve-storyboard")

        response = client.post(
            f"/projects/{project_id}/reject-render",
            json={"feedback": ["too low quality"], "quality_tier": "final"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "waiting_render_approval"


class _AlwaysFailingComputeProvider(IComputeProvider):
    provider_id = "always-failing"

    def submit(self, payload: EngineJobPayload) -> ComputeJobHandle:
        return ComputeJobHandle(provider_id=self.provider_id, external_job_id="doomed")

    def get_status(self, handle: ComputeJobHandle) -> ComputeJobStatus:
        return ComputeJobStatus.FAILED

    def fetch_output(self, handle: ComputeJobHandle) -> EngineJobOutput:
        raise AssertionError("should not be called")

    def cancel(self, handle: ComputeJobHandle) -> None:
        pass


def test_generation_failure_surfaces_as_failed_status_over_http():
    stack = build_stack(compute_provider=_AlwaysFailingComputeProvider())
    failing_state = AppState(
        project_store=stack.project_store,
        job_store=stack.job_store,
        asset_manager=stack.asset_manager,
        orchestrator=stack.orchestrator,
    )
    app.dependency_overrides[get_app_state] = lambda: failing_state
    try:
        with _client() as client:
            project = _create_project(client)
            project_id = project["project_id"]
            client.post(f"/projects/{project_id}/generate-plan")
            client.post(f"/projects/{project_id}/approve-storyboard")
            client.post(f"/projects/{project_id}/approve-render")

            response = client.post(f"/projects/{project_id}/generate-video")
            assert response.status_code == 200
            body = response.json()
            assert body["status"] == "failed"
            assert body["error_message"] is not None
    finally:
        app.dependency_overrides.pop(get_app_state, None)
