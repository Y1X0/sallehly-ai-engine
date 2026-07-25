from __future__ import annotations

from auth import User
from fastapi import Depends, Header, HTTPException, Request
from observability import context

from .state import AppState


def get_app_state(request: Request) -> AppState:
    return request.app.state.app_state


def get_current_user(
    authorization: str | None = Header(default=None),
    state: AppState = Depends(get_app_state),
) -> User:
    """Resolves the `Authorization: Bearer <token>` header via the app's
    `IAuthProvider`. Raises 401 if the header is missing/malformed or the
    token doesn't resolve to a user - never trusts client-supplied
    user/workspace ids directly (see routes/projects.py). Takes `state`
    via `Depends(get_app_state)` (rather than reading `request.app.state`
    directly) so `app.dependency_overrides[get_app_state]` in tests also
    redirects this dependency, not just routes that declare it explicitly.

    Sets `observability.context`'s `user_id` contextvar (Phase 8 WP1) so
    every log line emitted for the rest of this request - by the route
    handler, `ProjectLifecycle`, `GenerationPipeline` - carries it. Note
    this does NOT reach `ObservabilityMiddleware`'s own top-level
    request-summary log: `BaseHTTPMiddleware.call_next` runs the route
    handler in a separate task, and contextvar mutations made in a child
    task are never visible back in the parent after it returns (verified
    empirically - a Starlette/Python behavior, not a bug here)."""
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")

    token = authorization.removeprefix("Bearer ").strip()
    user = state.auth_provider.verify_token(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    context.set_user_id(user.user_id)
    return user
