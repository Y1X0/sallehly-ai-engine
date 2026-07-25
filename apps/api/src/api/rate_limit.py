from __future__ import annotations

from typing import Callable

from auth import User
from fastapi import Depends, HTTPException, Request
from observability.metrics import RATE_LIMIT_REJECTIONS_TOTAL

from .dependencies import get_app_state, get_current_user
from .state import AppState


def rate_limit_by_ip(scope: str, *, limit_attr: str) -> Callable[..., None]:
    """A FastAPI dependency limiting requests by client IP - for the
    pre-auth endpoints (`/auth/register`, `/auth/login`) where no
    authenticated user id exists yet to key by. `limit_attr` names the
    `AppState` field holding the per-minute limit (e.g.
    `"auth_rate_limit_per_minute"`) so call sites never hardcode a
    number that could drift from `Settings`. Phase 8 WP5, see
    docs/adr/0020-security-hardening.md."""

    def _dependency(request: Request, state: AppState = Depends(get_app_state)) -> None:
        limit = getattr(state, limit_attr)
        identity = request.client.host if request.client else "unknown"
        _enforce(state, f"{scope}:{identity}", limit, scope)

    return _dependency


def rate_limit_by_user(scope: str, *, limit_attr: str) -> Callable[..., None]:
    """Keys by authenticated user id - for the GPU-triggering endpoints
    (`generate-video`, `retry-generation`) where per-IP limiting would
    under-protect a single user hitting the API from a rotating or
    shared IP, and over-protect a NAT'd office of many real users behind
    one IP."""

    def _dependency(
        state: AppState = Depends(get_app_state), current_user: User = Depends(get_current_user)
    ) -> None:
        limit = getattr(state, limit_attr)
        _enforce(state, f"{scope}:{current_user.user_id}", limit, scope)

    return _dependency


def _enforce(state: AppState, key: str, limit: int, scope: str) -> None:
    result = state.rate_limiter.allow(key, limit=limit, window_seconds=60)
    if not result.allowed:
        RATE_LIMIT_REJECTIONS_TOTAL.labels(scope=scope).inc()
        raise HTTPException(
            status_code=429,
            detail="Too many requests",
            headers={"Retry-After": str(result.retry_after_seconds)},
        )
