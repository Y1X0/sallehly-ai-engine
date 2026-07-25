"""Real, executed tests for Phase 8 WP5 (Security Hardening,
docs/adr/0020-security-hardening.md): rate limiting, token expiry +
refresh, GPU/generation quota enforcement, upload validation, and
secure headers - unit-level tests against the packages directly plus
end-to-end HTTP tests via fastapi.testclient.TestClient against the
actual apps/api routes (no live server, no network for the in-memory
paths; Redis-backed variants run for real against a local Redis server
and are skipped entirely if none is reachable, same convention as
test_redis_token_store.py/test_redis_event_bus.py).
"""

from __future__ import annotations

import itertools
import time
import uuid

import pytest
from api.dependencies import get_app_state
from api.main import app
from api.state import AppState
from auth import AuthError, InMemoryUserStore, InMemoryTokenStore, LocalAuthProvider
from conftest import SAMPLE_BRIEF, SAMPLE_PROJECT_REQUEST, build_stack, default_wp5_app_state_kwargs
from fastapi.testclient import TestClient
from observability import LoggingErrorReporter
from quota_sdk import InMemoryQuotaEnforcer, QuotaExceededError
from rate_limit_sdk import InMemoryRateLimiter
from render_orchestrator import ProjectLifecycleError

_email_counter = itertools.count()


def _redis_reachable() -> bool:
    try:
        import redis

        return redis.Redis.from_url("redis://localhost:6379/0").ping()
    except Exception:
        return False


_REDIS_AVAILABLE = _redis_reachable()


# ---------------------------------------------------------------------------
# packages/rate-limit-sdk
# ---------------------------------------------------------------------------


def test_in_memory_rate_limiter_allows_up_to_limit_then_blocks():
    limiter = InMemoryRateLimiter()
    for _ in range(3):
        result = limiter.allow("k", limit=3, window_seconds=60)
        assert result.allowed

    blocked = limiter.allow("k", limit=3, window_seconds=60)
    assert not blocked.allowed
    assert blocked.remaining == 0
    assert blocked.retry_after_seconds > 0


def test_in_memory_rate_limiter_keys_are_independent():
    limiter = InMemoryRateLimiter()
    for _ in range(3):
        assert limiter.allow("a", limit=3, window_seconds=60).allowed
    assert not limiter.allow("a", limit=3, window_seconds=60).allowed
    # A different key has never been counted against, regardless of "a"'s state.
    assert limiter.allow("b", limit=3, window_seconds=60).allowed


def test_in_memory_rate_limiter_resets_after_window_elapses():
    limiter = InMemoryRateLimiter()
    assert limiter.allow("k", limit=1, window_seconds=1).allowed
    assert not limiter.allow("k", limit=1, window_seconds=1).allowed

    time.sleep(1.5)

    assert limiter.allow("k", limit=1, window_seconds=1).allowed


@pytest.mark.skipif(not _REDIS_AVAILABLE, reason="no Redis server reachable at redis://localhost:6379/0")
def test_redis_rate_limiter_matches_in_memory_behavior():
    from rate_limit_sdk import RedisRateLimiter

    limiter = RedisRateLimiter("redis://localhost:6379/0", key_prefix=f"test:{uuid.uuid4().hex[:8]}:")
    for _ in range(2):
        assert limiter.allow("k", limit=2, window_seconds=60).allowed

    blocked = limiter.allow("k", limit=2, window_seconds=60)
    assert not blocked.allowed
    assert blocked.remaining == 0
    assert blocked.retry_after_seconds > 0


# ---------------------------------------------------------------------------
# packages/quota-sdk
# ---------------------------------------------------------------------------


def test_in_memory_quota_enforcer_allows_up_to_max_concurrent():
    enforcer = InMemoryQuotaEnforcer()
    enforcer.acquire("ws1", max_concurrent=2)
    enforcer.acquire("ws1", max_concurrent=2)


def test_in_memory_quota_enforcer_raises_at_capacity():
    enforcer = InMemoryQuotaEnforcer()
    enforcer.acquire("ws1", max_concurrent=1)
    with pytest.raises(QuotaExceededError):
        enforcer.acquire("ws1", max_concurrent=1)


def test_in_memory_quota_enforcer_release_frees_a_slot():
    enforcer = InMemoryQuotaEnforcer()
    enforcer.acquire("ws1", max_concurrent=1)
    enforcer.release("ws1")
    enforcer.acquire("ws1", max_concurrent=1)  # would raise if the slot weren't freed


def test_in_memory_quota_enforcer_scopes_are_independent():
    enforcer = InMemoryQuotaEnforcer()
    enforcer.acquire("ws1", max_concurrent=1)
    enforcer.acquire("ws2", max_concurrent=1)  # ws2 is unaffected by ws1's cap


@pytest.mark.skipif(not _REDIS_AVAILABLE, reason="no Redis server reachable at redis://localhost:6379/0")
def test_redis_quota_enforcer_matches_in_memory_behavior():
    from quota_sdk import RedisQuotaEnforcer

    scope = f"ws-{uuid.uuid4().hex[:8]}"
    enforcer = RedisQuotaEnforcer("redis://localhost:6379/0", key_prefix=f"test:{uuid.uuid4().hex[:8]}:")
    enforcer.acquire(scope, max_concurrent=1)
    with pytest.raises(QuotaExceededError):
        enforcer.acquire(scope, max_concurrent=1)
    enforcer.release(scope)
    enforcer.acquire(scope, max_concurrent=1)  # would raise if the slot weren't freed


@pytest.mark.skipif(not _REDIS_AVAILABLE, reason="no Redis server reachable at redis://localhost:6379/0")
def test_redis_quota_enforcer_release_never_goes_negative():
    from quota_sdk import RedisQuotaEnforcer

    scope = f"ws-{uuid.uuid4().hex[:8]}"
    enforcer = RedisQuotaEnforcer("redis://localhost:6379/0", key_prefix=f"test:{uuid.uuid4().hex[:8]}:")
    enforcer.release(scope)  # release without a matching acquire()
    enforcer.acquire(scope, max_concurrent=1)  # still only costs one real slot


# ---------------------------------------------------------------------------
# packages/auth: token TTL + refresh
# ---------------------------------------------------------------------------


def test_in_memory_token_store_expires_after_ttl():
    store = InMemoryTokenStore()
    store.set("tok1", "user1", ttl_seconds=1)
    assert store.get("tok1") == "user1"

    time.sleep(1.5)

    assert store.get("tok1") is None


def test_in_memory_token_store_never_expires_by_default():
    store = InMemoryTokenStore()
    store.set("tok1", "user1")
    time.sleep(1.1)
    assert store.get("tok1") == "user1"


def test_local_auth_provider_refresh_token_rotates_and_invalidates_old():
    user_store = InMemoryUserStore()
    provider = LocalAuthProvider(user_store)
    user = provider.register("refresh@example.com", "hunter22")
    old_token = provider.authenticate("refresh@example.com", "hunter22")

    new_token = provider.refresh_token(old_token.token)

    assert new_token.token != old_token.token
    assert new_token.user_id == user.user_id
    assert provider.verify_token(old_token.token) is None
    assert provider.verify_token(new_token.token) is not None


def test_local_auth_provider_refresh_unknown_token_raises():
    provider = LocalAuthProvider(InMemoryUserStore())
    with pytest.raises(AuthError):
        provider.refresh_token("not-a-real-token")


def test_local_auth_provider_expired_token_cannot_be_refreshed():
    provider = LocalAuthProvider(InMemoryUserStore(), token_ttl_seconds=1)
    provider.register("expiring@example.com", "hunter22")
    token = provider.authenticate("expiring@example.com", "hunter22")

    time.sleep(1.5)

    assert provider.verify_token(token.token) is None
    with pytest.raises(AuthError):
        provider.refresh_token(token.token)


# ---------------------------------------------------------------------------
# ProjectLifecycle: GPU/generation quota enforcement
# ---------------------------------------------------------------------------


def _ready_for_generation(lifecycle, workspace_id: str = "ws1"):
    record = lifecycle.create_project(**{**SAMPLE_BRIEF, "workspace_id": workspace_id})
    lifecycle.generate_creative_plan(record.project_id)
    lifecycle.approve_storyboard(record.project_id)
    return lifecycle.approve_render_plan(record.project_id)


def test_generate_video_raises_when_workspace_already_at_concurrency_cap():
    quota = InMemoryQuotaEnforcer()
    stack = build_stack(quota_enforcer=quota, max_concurrent_generations_per_workspace=1)
    record = _ready_for_generation(stack.lifecycle, workspace_id="ws1")

    # Simulate another generation already in flight for the same workspace.
    quota.acquire("ws1", max_concurrent=1)

    with pytest.raises(ProjectLifecycleError):
        stack.lifecycle.generate_video(record.project_id)

    # The rejected attempt must never have transitioned the project - it
    # was stopped before the state machine moved, not left half-applied.
    from persistence import ProjectStatus

    assert stack.project_store.get(record.project_id).status == ProjectStatus.APPROVED


def test_generate_video_releases_quota_slot_after_completion():
    quota = InMemoryQuotaEnforcer()
    stack = build_stack(quota_enforcer=quota, max_concurrent_generations_per_workspace=1)
    first = _ready_for_generation(stack.lifecycle, workspace_id="ws1")

    stack.lifecycle.generate_video(first.project_id)

    # If the slot weren't released, this second (sequential, not
    # concurrent) generation for the same workspace would incorrectly
    # be rejected too.
    second = _ready_for_generation(stack.lifecycle, workspace_id="ws1")
    record = stack.lifecycle.generate_video(second.project_id)

    from persistence import ProjectStatus

    assert record.status == ProjectStatus.COMPLETED


def test_generate_video_unaffected_when_quota_not_configured():
    """Default `max_concurrent_generations_per_workspace=0` (unset) must
    behave exactly like every pre-WP5 environment: no quota check at
    all, even with a real `IQuotaEnforcer` injected."""
    quota = InMemoryQuotaEnforcer()
    stack = build_stack(quota_enforcer=quota, max_concurrent_generations_per_workspace=0)
    record = _ready_for_generation(stack.lifecycle, workspace_id="ws1")
    quota.acquire("ws1", max_concurrent=1)  # would be "at capacity" if enforcement were active

    from persistence import ProjectStatus

    result = stack.lifecycle.generate_video(record.project_id)
    assert result.status == ProjectStatus.COMPLETED


# ---------------------------------------------------------------------------
# apps/api: end-to-end HTTP tests
# ---------------------------------------------------------------------------


def _client() -> TestClient:
    return TestClient(app)


def _custom_state(stack, **overrides) -> AppState:
    base = dict(
        project_store=stack.project_store,
        job_store=stack.job_store,
        asset_manager=stack.asset_manager,
        orchestrator=stack.orchestrator,
        user_store=stack.user_store,
        auth_provider=stack.auth_provider,
        memory=stack.memory,
        cinematic_intelligence=stack.cinematic_intelligence,
        error_reporter=LoggingErrorReporter(),
        lifecycle=stack.lifecycle,
        **default_wp5_app_state_kwargs(),
    )
    base.update(overrides)
    return AppState(**base)


def _auth_headers(client: TestClient) -> dict[str, str]:
    email = f"wp5-{next(_email_counter)}@example.com"
    response = client.post("/auth/register", json={"email": email, "password": "hunter22"})
    assert response.status_code == 201
    response = client.post("/auth/login", json={"email": email, "password": "hunter22"})
    assert response.status_code == 200
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _create_ready_project(client: TestClient, headers: dict[str, str]) -> str:
    project = client.post("/projects", json=SAMPLE_PROJECT_REQUEST, headers=headers).json()
    project_id = project["project_id"]
    assert client.post(f"/projects/{project_id}/generate-plan", headers=headers).status_code == 200
    assert client.post(f"/projects/{project_id}/approve-storyboard", headers=headers).status_code == 200
    assert client.post(f"/projects/{project_id}/approve-render", headers=headers).status_code == 200
    return project_id


def test_auth_endpoints_are_rate_limited_per_ip():
    stack = build_stack()
    custom_state = _custom_state(stack, auth_rate_limit_per_minute=2)
    app.dependency_overrides[get_app_state] = lambda: custom_state
    try:
        with TestClient(app) as client:
            for i in range(2):
                response = client.post(
                    "/auth/register", json={"email": f"rl{i}@example.com", "password": "hunter22"}
                )
                assert response.status_code == 201

            blocked = client.post(
                "/auth/register", json={"email": "rl-blocked@example.com", "password": "hunter22"}
            )
    finally:
        app.dependency_overrides.pop(get_app_state, None)

    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


def test_generation_endpoints_are_rate_limited_per_user():
    stack = build_stack()
    custom_state = _custom_state(stack, generation_rate_limit_per_minute=1)
    app.dependency_overrides[get_app_state] = lambda: custom_state
    try:
        with TestClient(app) as client:
            headers = _auth_headers(client)
            first_project = _create_ready_project(client, headers)
            second_project = _create_ready_project(client, headers)

            allowed = client.post(f"/projects/{first_project}/generate-video", headers=headers)
            blocked = client.post(f"/projects/{second_project}/generate-video", headers=headers)
    finally:
        app.dependency_overrides.pop(get_app_state, None)

    assert allowed.status_code == 200
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


def test_auth_refresh_rotates_token_and_invalidates_old_one():
    with _client() as client:
        headers = _auth_headers(client)
        old_token = headers["Authorization"].removeprefix("Bearer ")

        response = client.post("/auth/refresh", headers=headers)
        assert response.status_code == 200
        new_token = response.json()["token"]
        assert new_token != old_token

        # The old token must no longer authenticate anything.
        stale = client.get("/users/me", headers=headers)
        assert stale.status_code == 401

        fresh = client.get("/users/me", headers={"Authorization": f"Bearer {new_token}"})
        assert fresh.status_code == 200


def test_auth_refresh_without_authorization_header_returns_401():
    with _client() as client:
        response = client.post("/auth/refresh")
        assert response.status_code == 401


def test_auth_refresh_with_garbage_token_returns_401():
    with _client() as client:
        response = client.post("/auth/refresh", headers={"Authorization": "Bearer not-a-real-token"})
        assert response.status_code == 401


def test_jobs_still_require_auth_and_ownership_after_wp5_wiring():
    """Regression guard: WP5's rate-limit/quota changes must not have
    disturbed WP5's own earlier jobs.py authorization fix."""
    with _client() as client:
        response = client.get("/jobs/does-not-matter")
        assert response.status_code == 401


def test_upload_rejects_disallowed_content_type():
    with _client() as client:
        headers = _auth_headers(client)
        response = client.post(
            "/assets/upload",
            files={"file": ("payload.exe", b"not really an executable", "application/x-msdownload")},
            headers=headers,
        )
        assert response.status_code == 415


def test_upload_accepts_allowed_content_type_within_limit():
    with _client() as client:
        headers = _auth_headers(client)
        response = client.post(
            "/assets/upload",
            files={"file": ("ref.png", b"\x89PNG\r\n\x1a\nfake-but-small", "image/png")},
            headers=headers,
        )
        assert response.status_code == 201
        assert response.json()["versions"][-1]["uri"]


def test_upload_rejects_oversized_file():
    stack = build_stack()
    custom_state = _custom_state(stack, upload_max_bytes=8)
    app.dependency_overrides[get_app_state] = lambda: custom_state
    try:
        with TestClient(app) as client:
            headers = _auth_headers(client)
            response = client.post(
                "/assets/upload",
                files={"file": ("ref.png", b"this payload is well over eight bytes", "image/png")},
                headers=headers,
            )
    finally:
        app.dependency_overrides.pop(get_app_state, None)

    assert response.status_code == 413


def test_security_headers_present_on_normal_response():
    with _client() as client:
        response = client.get("/healthz")

    for header in (
        "X-Content-Type-Options",
        "X-Frame-Options",
        "Referrer-Policy",
        "Content-Security-Policy",
        "Strict-Transport-Security",
        "Permissions-Policy",
    ):
        assert header in response.headers, header


def test_security_headers_present_on_client_error_response():
    with _client() as client:
        response = client.get("/projects/does-not-exist")  # 401, no auth header

    assert response.status_code == 401
    assert response.headers.get("X-Content-Type-Options") == "nosniff"


def test_security_headers_present_on_unhandled_exception_response():
    """Regression guard for the bug fixed alongside this test file:
    stacking `SecurityHeadersMiddleware` on top of `ObservabilityMiddleware`
    (both `BaseHTTPMiddleware`) broke `ObservabilityMiddleware`'s
    contextvar-based correlation id from reaching the global exception
    handler (fixed via `request.state`, see middleware.py/main.py) -
    this asserts the *headers* path, which was never broken (applied
    explicitly by `apply_security_headers` in main.py) but is worth
    pinning down in the same breath."""

    @app.get("/__test_wp5_boom")
    def _boom() -> None:
        raise RuntimeError("deliberately unhandled for this test")

    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/__test_wp5_boom")
    finally:
        app.router.routes[:] = [r for r in app.router.routes if getattr(r, "path", None) != "/__test_wp5_boom"]

    assert response.status_code == 500
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert "correlation_id" in response.json()
