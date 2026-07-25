"""API contract tests for the Phase 8 Cinematic Intelligence routes
(apps/api/src/api/routes/cinematic.py) and the finalize/render-manifest
routes added to routes/projects.py - real HTTP requests via
fastapi.testclient.TestClient against the real app, exercising a real
CinematicIntelligenceCoordinator (build_app_state() wires one
unconditionally - see apps/api/src/api/state.py).
"""

from __future__ import annotations

import itertools

from api.dependencies import get_app_state
from api.main import app
from api.state import AppState
from conftest import SAMPLE_PROJECT_REQUEST, build_stack, default_wp5_app_state_kwargs
from fastapi.testclient import TestClient
from media_helpers import FFMPEG_AVAILABLE, make_color_clip
from observability import LoggingErrorReporter
import pytest

_email_counter = itertools.count()


def _client() -> TestClient:
    return TestClient(app)


def _auth_headers(client: TestClient) -> dict[str, str]:
    email = f"cinetester{next(_email_counter)}@example.com"
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


def _project_with_render_plan(client: TestClient, headers: dict[str, str]) -> tuple[str, list[str]]:
    """Drives a fresh project through generate-plan -> approve-storyboard
    (the point at which ProjectLifecycle._enrich_render_plan has already
    run CIL against the real compiled RenderPlan) and returns
    (project_id, shot_ids)."""
    project = _create_project(client, headers)
    project_id = project["project_id"]
    client.post(f"/projects/{project_id}/generate-plan", headers=headers)
    client.post(f"/projects/{project_id}/approve-storyboard", headers=headers)
    render_plan = client.get(f"/projects/{project_id}/render-plan", headers=headers).json()
    shot_ids = [spec["shot_id"] for spec in render_plan["render_specs"]]
    return project_id, shot_ids


def test_analyze_and_report_return_the_same_live_aggregation():
    with _client() as client:
        headers = _auth_headers(client)
        project_id, _ = _project_with_render_plan(client, headers)

        analyze_response = client.post(f"/projects/{project_id}/cinematic/analyze", headers=headers)
        assert analyze_response.status_code == 200
        report_response = client.get(f"/projects/{project_id}/cinematic/report", headers=headers)
        assert report_response.status_code == 200

        analyze_body = analyze_response.json()
        assert analyze_body == report_response.json()
        assert analyze_body["shots_analyzed"] > 0
        assert "overall" in analyze_body["scores"]


def test_cinematic_routes_require_auth():
    with _client() as client:
        assert client.post("/projects/does-not-exist/cinematic/analyze").status_code == 401
        assert client.get("/projects/does-not-exist/cinematic/report").status_code == 401


def test_cinematic_routes_require_ownership():
    with _client() as client:
        owner_headers = _auth_headers(client)
        project_id, _ = _project_with_render_plan(client, owner_headers)

        other_headers = _auth_headers(client)
        assert client.post(f"/projects/{project_id}/cinematic/analyze", headers=other_headers).status_code == 403
        assert client.get(f"/projects/{project_id}/cinematic/report", headers=other_headers).status_code == 403


def test_analyze_missing_project_returns_404():
    with _client() as client:
        headers = _auth_headers(client)
        response = client.post("/projects/does-not-exist/cinematic/analyze", headers=headers)
        assert response.status_code == 404


def test_improve_prompt_bumps_version_and_unknown_shot_returns_404():
    with _client() as client:
        headers = _auth_headers(client)
        project_id, shot_ids = _project_with_render_plan(client, headers)

        response = client.post(
            f"/projects/{project_id}/cinematic/prompts/{shot_ids[0]}/improve", headers=headers
        )
        assert response.status_code == 200
        assert response.json()["version"] == 2

        missing = client.post(
            f"/projects/{project_id}/cinematic/prompts/does-not-exist/improve", headers=headers
        )
        assert missing.status_code == 404


def test_repair_shot_for_unknown_shot_returns_404():
    with _client() as client:
        headers = _auth_headers(client)
        project_id, _ = _project_with_render_plan(client, headers)

        # repair_shot requires a QualityReport to already exist for the
        # shot (see CinematicIntelligenceCoordinator.repair_shot's
        # docstring); enrich_render_plan (which already ran during
        # approve-storyboard) records one per real shot automatically, so
        # only a shot id that was never part of this project 404s.
        response = client.post(f"/projects/{project_id}/cinematic/repair/does-not-exist", headers=headers)
        assert response.status_code == 404


def test_repair_shot_full_flow_over_http():
    with _client() as client:
        headers = _auth_headers(client)
        project_id, shot_ids = _project_with_render_plan(client, headers)

        repair_response = client.post(f"/projects/{project_id}/cinematic/repair/{shot_ids[0]}", headers=headers)
        assert repair_response.status_code == 200
        action = repair_response.json()
        assert action["shot_id"] == shot_ids[0]
        assert action["review_status"] == "pending"

        listed = client.get(f"/projects/{project_id}/cinematic/repairs", headers=headers)
        assert listed.status_code == 200
        assert len(listed.json()["repairs"]) == 1

        approve_response = client.post(
            f"/projects/{project_id}/cinematic/repairs/{action['repair_id']}/approve", headers=headers
        )
        assert approve_response.status_code == 200
        assert approve_response.json()["review_status"] == "approved"


def test_list_repairs_empty_for_a_project_with_no_repairs():
    with _client() as client:
        headers = _auth_headers(client)
        project_id, _ = _project_with_render_plan(client, headers)

        response = client.get(f"/projects/{project_id}/cinematic/repairs", headers=headers)
        assert response.status_code == 200
        assert response.json() == {"repairs": []}


def test_approve_and_reject_repair_require_a_real_repair_id():
    with _client() as client:
        headers = _auth_headers(client)
        project_id, _ = _project_with_render_plan(client, headers)

        approve = client.post(
            f"/projects/{project_id}/cinematic/repairs/does-not-exist/approve", headers=headers
        )
        assert approve.status_code == 404
        reject = client.post(
            f"/projects/{project_id}/cinematic/repairs/does-not-exist/reject", headers=headers
        )
        assert reject.status_code == 404


def test_finalize_before_completed_returns_409():
    with _client() as client:
        headers = _auth_headers(client)
        project = _create_project(client, headers)
        response = client.post(f"/projects/{project['project_id']}/finalize", json={}, headers=headers)
        assert response.status_code == 409


def test_render_manifest_before_finalize_returns_404():
    with _client() as client:
        headers = _auth_headers(client)
        project = _create_project(client, headers)
        response = client.get(f"/projects/{project['project_id']}/render-manifest", headers=headers)
        assert response.status_code == 404


def test_finalize_requires_ownership():
    with _client() as client:
        owner_headers = _auth_headers(client)
        project = _create_project(client, owner_headers)

        other_headers = _auth_headers(client)
        response = client.post(f"/projects/{project['project_id']}/finalize", json={}, headers=other_headers)
        assert response.status_code == 403


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg not installed - see docs/DEV_SETUP.md")
def test_finalize_and_render_manifest_succeed_over_http(tmp_path):
    # build_app_state()'s default LocalProvider writes placeholder JSON
    # (not real video bytes), so - exactly as in
    # tests/test_project_lifecycle.py's equivalent lifecycle-level test -
    # this swaps in a custom AppState via dependency_overrides so real
    # ffmpeg-generated clips can be registered as each shot's *latest*
    # AssetManager version before calling /finalize, proving the full
    # HTTP-facing finalize -> render-manifest path is genuinely wired end
    # to end, not just the lower-level PostProductionRunner.
    stack = build_stack(with_cinematic_intelligence=True, with_post_production=True)
    custom_state = AppState(
        project_store=stack.project_store,
        job_store=stack.job_store,
        asset_manager=stack.asset_manager,
        orchestrator=stack.orchestrator,
        user_store=stack.user_store,
        auth_provider=stack.auth_provider,
        cinematic_intelligence=stack.cinematic_intelligence,
        error_reporter=LoggingErrorReporter(),
        memory=stack.memory,
        lifecycle=stack.lifecycle,
        **default_wp5_app_state_kwargs(),
    )
    app.dependency_overrides[get_app_state] = lambda: custom_state
    try:
        with _client() as client:
            headers = _auth_headers(client)
            project_id, shot_ids = _project_with_render_plan(client, headers)
            client.post(f"/projects/{project_id}/approve-render", headers=headers)
            generate_response = client.post(f"/projects/{project_id}/generate-video", headers=headers)
            assert generate_response.json()["status"] == "completed"

            for index, shot_id in enumerate(shot_ids):
                clip_path = make_color_clip(
                    tmp_path / f"{shot_id}.mp4", "red" if index % 2 == 0 else "blue", duration=2.0
                )
                stack.asset_manager.register(project_id, kind="video", shot_id=shot_id, uri=clip_path)

            finalize_response = client.post(f"/projects/{project_id}/finalize", json={}, headers=headers)
            assert finalize_response.status_code == 200
            body = finalize_response.json()
            assert body["status"] == "exported"
            assert body["render_manifest"]["video"]["format"] == "mp4"

            manifest_response = client.get(f"/projects/{project_id}/render-manifest", headers=headers)
            assert manifest_response.status_code == 200
            assert manifest_response.json() == body["render_manifest"]
    finally:
        app.dependency_overrides.pop(get_app_state, None)
