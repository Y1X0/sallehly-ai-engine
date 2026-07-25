"""Real, executed integration tests for Phase 8 WP1's apps/api wiring:
ObservabilityMiddleware (correlation id, request metrics, tracing) and
the global exception handler - real HTTP requests via
fastapi.testclient.TestClient against the actual app, not mocked.
"""

from __future__ import annotations

from api.dependencies import get_app_state
from api.main import app
from api.state import AppState
from conftest import build_stack
from fastapi.testclient import TestClient
from observability import IErrorReporter, render_metrics


def _client() -> TestClient:
    return TestClient(app)


def test_correlation_id_is_generated_and_echoed_when_absent():
    with _client() as client:
        response = client.get("/healthz")
        assert response.status_code == 200
        correlation_id = response.headers.get("x-correlation-id")
        assert correlation_id
        assert len(correlation_id) == 16


def test_correlation_id_is_propagated_when_caller_supplies_one():
    with _client() as client:
        response = client.get("/healthz", headers={"X-Correlation-ID": "caller-supplied-id"})
        assert response.headers.get("x-correlation-id") == "caller-supplied-id"


def test_metrics_endpoint_reflects_real_request_counts():
    with _client() as client:
        before_body, _ = render_metrics()
        client.get("/healthz")
        client.get("/healthz")
        response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.content
    assert body != before_body
    assert b'path="/healthz"' in body
    assert b"sallehly_http_requests_total" in body
    assert b"sallehly_http_request_duration_seconds" in body


class _SpyErrorReporter(IErrorReporter):
    def __init__(self) -> None:
        self.captured: list[BaseException] = []

    def capture_exception(self, exc: BaseException, *, extra=None) -> None:
        self.captured.append(exc)


def test_unhandled_exception_returns_generic_body_with_correlation_id_and_reports_it():
    stack = build_stack()
    spy = _SpyErrorReporter()
    custom_state = AppState(
        project_store=stack.project_store,
        job_store=stack.job_store,
        asset_manager=stack.asset_manager,
        orchestrator=stack.orchestrator,
        user_store=stack.user_store,
        auth_provider=stack.auth_provider,
        cinematic_intelligence=stack.cinematic_intelligence,
        error_reporter=spy,
        memory=stack.memory,
        lifecycle=stack.lifecycle,
    )

    @app.get("/__test_boom")
    def _boom() -> None:
        raise RuntimeError("kaboom - deliberately unhandled for this test")

    # dependency_overrides only reaches `Depends(get_app_state)` - the
    # global exception handler in main.py isn't part of FastAPI's
    # dependency graph (exception handlers only ever receive
    # `(request, exc)`), so it reads `request.app.state.app_state`
    # directly. Patching that attribute (after the lifespan has already
    # set the real default one) is the only way to make it see our spy.
    with TestClient(app, raise_server_exceptions=False) as client:
        original_state = app.state.app_state
        app.state.app_state = custom_state
        try:
            response = client.get("/__test_boom")
        finally:
            app.state.app_state = original_state
            app.router.routes[:] = [r for r in app.router.routes if getattr(r, "path", None) != "/__test_boom"]

    assert response.status_code == 500
    body = response.json()
    assert body["detail"] == "Internal server error"
    assert "correlation_id" in body
    assert "kaboom" not in response.text

    assert len(spy.captured) == 1
    assert isinstance(spy.captured[0], RuntimeError)
    assert str(spy.captured[0]) == "kaboom - deliberately unhandled for this test"


def test_business_rule_rejection_is_not_reported_as_an_unhandled_error():
    """A 409 ProjectLifecycleError is an expected business-rule
    rejection, already handled by routes/projects.py's own
    try/except - it must never reach the global exception handler or
    IErrorReporter."""
    stack = build_stack()
    spy = _SpyErrorReporter()
    custom_state = AppState(
        project_store=stack.project_store,
        job_store=stack.job_store,
        asset_manager=stack.asset_manager,
        orchestrator=stack.orchestrator,
        user_store=stack.user_store,
        auth_provider=stack.auth_provider,
        cinematic_intelligence=stack.cinematic_intelligence,
        error_reporter=spy,
        memory=stack.memory,
        lifecycle=stack.lifecycle,
    )
    app.dependency_overrides[get_app_state] = lambda: custom_state
    try:
        with TestClient(app) as client:
            register = client.post("/auth/register", json={"email": "obs@example.com", "password": "hunter22"})
            login = client.post("/auth/login", json={"email": "obs@example.com", "password": "hunter22"})
            headers = {"Authorization": f"Bearer {login.json()['token']}"}
            project = client.post(
                "/projects",
                json={"prompt": "x", "target_duration_sec": 10, "aspect_ratio": "16:9"},
                headers=headers,
            ).json()
            # approve-storyboard before a plan even exists -> ProjectLifecycleError -> 409
            response = client.post(f"/projects/{project['project_id']}/approve-storyboard", headers=headers)
    finally:
        app.dependency_overrides.pop(get_app_state, None)

    assert register.status_code == 201
    assert response.status_code == 409
    assert spy.captured == []
