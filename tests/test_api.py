"""End-to-end API contract tests: real HTTP requests via
fastapi.testclient.TestClient (no live server, no network) against the
actual apps/api routes, wired to the fully offline default stack
(LocalHeuristicLLMProvider + Wan21Adapter + LocalProvider).
"""

from __future__ import annotations

import itertools

from api.dependencies import get_app_state
from api.main import app
from api.state import AppState
from conftest import SAMPLE_PROJECT_REQUEST, build_stack
from fastapi.testclient import TestClient
from video_engine_sdk import ComputeJobHandle, ComputeJobStatus, EngineJobOutput, EngineJobPayload, IComputeProvider

_email_counter = itertools.count()


def _client() -> TestClient:
    return TestClient(app)


def _auth_headers(client: TestClient) -> dict[str, str]:
    email = f"tester{next(_email_counter)}@example.com"
    response = client.post("/auth/register", json={"email": email, "password": "hunter22"})
    assert response.status_code == 201
    response = client.post("/auth/login", json={"email": email, "password": "hunter22"})
    assert response.status_code == 200
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _create_project(client: TestClient, headers: dict[str, str]) -> dict:
    response = client.post("/projects", json=SAMPLE_PROJECT_REQUEST, headers=headers)
    assert response.status_code == 201
    return response.json()


def test_create_and_get_project():
    with _client() as client:
        headers = _auth_headers(client)
        project = _create_project(client, headers)
        assert project["status"] == "created"

        response = client.get(f"/projects/{project['project_id']}", headers=headers)
        assert response.status_code == 200
        assert response.json()["project_id"] == project["project_id"]


def test_project_routes_require_auth():
    with _client() as client:
        response = client.post("/projects", json=SAMPLE_PROJECT_REQUEST)
        assert response.status_code == 401

        response = client.get("/projects/does-not-exist")
        assert response.status_code == 401


def test_cannot_access_another_users_project():
    with _client() as client:
        owner_headers = _auth_headers(client)
        project = _create_project(client, owner_headers)

        other_headers = _auth_headers(client)
        response = client.get(f"/projects/{project['project_id']}", headers=other_headers)
        assert response.status_code == 403


def test_get_missing_project_returns_404():
    with _client() as client:
        headers = _auth_headers(client)
        response = client.get("/projects/does-not-exist", headers=headers)
        assert response.status_code == 404


def test_approve_storyboard_before_plan_returns_409():
    with _client() as client:
        headers = _auth_headers(client)
        project = _create_project(client, headers)
        response = client.post(f"/projects/{project['project_id']}/approve-storyboard", headers=headers)
        assert response.status_code == 409


def test_full_lifecycle_over_http_reaches_completed_with_assets_and_jobs():
    with _client() as client:
        headers = _auth_headers(client)
        project = _create_project(client, headers)
        project_id = project["project_id"]

        response = client.post(f"/projects/{project_id}/generate-plan", headers=headers)
        assert response.status_code == 200
        assert response.json()["status"] == "waiting_storyboard_approval"

        response = client.post(f"/projects/{project_id}/approve-storyboard", headers=headers)
        assert response.status_code == 200
        assert response.json()["status"] == "waiting_render_approval"

        response = client.post(f"/projects/{project_id}/approve-render", headers=headers)
        assert response.status_code == 200
        assert response.json()["status"] == "approved"

        response = client.post(f"/projects/{project_id}/generate-video", headers=headers)
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

        response = client.get(f"/projects/{project_id}/assets", headers=headers)
        assert response.status_code == 200
        assets_body = response.json()
        assert assets_body["project_id"] == project_id
        assert len(assets_body["assets"]) == len(asset_ids)


def test_plan_storyboard_and_render_plan_are_retrievable_over_http():
    with _client() as client:
        headers = _auth_headers(client)
        project = _create_project(client, headers)
        project_id = project["project_id"]

        # not generated yet
        assert client.get(f"/projects/{project_id}/plan", headers=headers).status_code == 404
        assert client.get(f"/projects/{project_id}/storyboard", headers=headers).status_code == 404
        assert client.get(f"/projects/{project_id}/render-plan", headers=headers).status_code == 404

        client.post(f"/projects/{project_id}/generate-plan", headers=headers)

        plan = client.get(f"/projects/{project_id}/plan", headers=headers)
        assert plan.status_code == 200
        assert plan.json()["project_id"] == project_id

        storyboard = client.get(f"/projects/{project_id}/storyboard", headers=headers)
        assert storyboard.status_code == 200
        assert len(storyboard.json()["frames"]) > 0

        # render plan doesn't exist until the storyboard gate is approved
        assert client.get(f"/projects/{project_id}/render-plan", headers=headers).status_code == 404

        client.post(f"/projects/{project_id}/approve-storyboard", headers=headers)

        render_plan = client.get(f"/projects/{project_id}/render-plan", headers=headers)
        assert render_plan.status_code == 200
        assert len(render_plan.json()["render_specs"]) > 0


def test_plan_storyboard_render_plan_require_ownership():
    with _client() as client:
        owner_headers = _auth_headers(client)
        project = _create_project(client, owner_headers)
        client.post(f"/projects/{project['project_id']}/generate-plan", headers=owner_headers)

        other_headers = _auth_headers(client)
        assert client.get(f"/projects/{project['project_id']}/plan", headers=other_headers).status_code == 403
        assert (
            client.get(f"/projects/{project['project_id']}/storyboard", headers=other_headers).status_code == 403
        )
        assert (
            client.get(f"/projects/{project['project_id']}/render-plan", headers=other_headers).status_code == 403
        )


def test_get_missing_job_returns_404():
    with _client() as client:
        response = client.get("/jobs/does-not-exist")
        assert response.status_code == 404
        response = client.get("/jobs/does-not-exist/status")
        assert response.status_code == 404


def test_register_login_and_get_me():
    with _client() as client:
        email = f"tester{next(_email_counter)}@example.com"
        response = client.post("/auth/register", json={"email": email, "password": "hunter22"})
        assert response.status_code == 201
        user = response.json()
        assert user["email"] == email
        assert "password_hash" not in user

        response = client.post("/auth/login", json={"email": email, "password": "wrong-password"})
        assert response.status_code == 401

        response = client.post("/auth/login", json={"email": email, "password": "hunter22"})
        assert response.status_code == 200
        token = response.json()["token"]

        response = client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert response.json()["user_id"] == user["user_id"]


def test_register_duplicate_email_returns_409():
    with _client() as client:
        email = f"tester{next(_email_counter)}@example.com"
        client.post("/auth/register", json={"email": email, "password": "hunter22"})
        response = client.post("/auth/register", json={"email": email, "password": "hunter22"})
        assert response.status_code == 409


def test_list_projects_scoped_to_callers_own_workspace():
    with _client() as client:
        headers = _auth_headers(client)
        _create_project(client, headers)
        _create_project(client, headers)

        other_headers = _auth_headers(client)
        _create_project(client, other_headers)

        response = client.get("/projects", headers=headers)
        assert response.status_code == 200
        assert len(response.json()["projects"]) == 2

        response = client.get("/projects", headers=other_headers)
        assert response.status_code == 200
        assert len(response.json()["projects"]) == 1


def test_retry_generation_requires_failed_status_over_http():
    with _client() as client:
        headers = _auth_headers(client)
        project = _create_project(client, headers)
        response = client.post(f"/projects/{project['project_id']}/retry-generation", headers=headers)
        assert response.status_code == 409


def test_upload_asset_and_reference_it_in_a_new_project():
    with _client() as client:
        headers = _auth_headers(client)

        response = client.post(
            "/assets/upload",
            files={"file": ("ref.png", b"fake-png-bytes", "image/png")},
            headers=headers,
        )
        assert response.status_code == 201
        asset = response.json()
        assert asset["kind"] == "image"
        asset_id = asset["asset_id"]

        body = {**SAMPLE_PROJECT_REQUEST, "reference_asset_ids": [asset_id]}
        response = client.post("/projects", json=body, headers=headers)
        assert response.status_code == 201
        assert response.json()["brief"]["reference_asset_ids"] == [asset_id]


def test_upload_asset_requires_auth():
    with _client() as client:
        response = client.post("/assets/upload", files={"file": ("ref.png", b"bytes", "image/png")})
        assert response.status_code == 401


def test_upload_asset_for_someone_elses_project_returns_403():
    with _client() as client:
        owner_headers = _auth_headers(client)
        project = _create_project(client, owner_headers)

        other_headers = _auth_headers(client)
        response = client.post(
            "/assets/upload",
            files={"file": ("ref.png", b"bytes", "image/png")},
            data={"project_id": project["project_id"]},
            headers=other_headers,
        )
        assert response.status_code == 403


def test_reject_storyboard_over_http_regenerates_and_stays_at_gate_one():
    with _client() as client:
        headers = _auth_headers(client)
        project = _create_project(client, headers)
        project_id = project["project_id"]
        client.post(f"/projects/{project_id}/generate-plan", headers=headers)

        response = client.post(
            f"/projects/{project_id}/reject-storyboard", json={"feedback": ["too static"]}, headers=headers
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "waiting_storyboard_approval"
        assert body["rejected_stage"] is None


def test_reject_render_over_http_with_quality_tier_override():
    with _client() as client:
        headers = _auth_headers(client)
        project = _create_project(client, headers)
        project_id = project["project_id"]
        client.post(f"/projects/{project_id}/generate-plan", headers=headers)
        client.post(f"/projects/{project_id}/approve-storyboard", headers=headers)

        response = client.post(
            f"/projects/{project_id}/reject-render",
            json={"feedback": ["too low quality"], "quality_tier": "final"},
            headers=headers,
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
    stack = build_stack(compute_provider=_AlwaysFailingComputeProvider(), with_cinematic_intelligence=True)
    failing_state = AppState(
        project_store=stack.project_store,
        job_store=stack.job_store,
        asset_manager=stack.asset_manager,
        orchestrator=stack.orchestrator,
        user_store=stack.user_store,
        auth_provider=stack.auth_provider,
        cinematic_intelligence=stack.cinematic_intelligence,
        memory=stack.memory,
        lifecycle=stack.lifecycle,
    )
    app.dependency_overrides[get_app_state] = lambda: failing_state
    try:
        with _client() as client:
            headers = _auth_headers(client)
            project = _create_project(client, headers)
            project_id = project["project_id"]
            client.post(f"/projects/{project_id}/generate-plan", headers=headers)
            client.post(f"/projects/{project_id}/approve-storyboard", headers=headers)
            client.post(f"/projects/{project_id}/approve-render", headers=headers)

            response = client.post(f"/projects/{project_id}/generate-video", headers=headers)
            assert response.status_code == 200
            body = response.json()
            assert body["status"] == "failed"
            assert body["error_message"] is not None
    finally:
        app.dependency_overrides.pop(get_app_state, None)
