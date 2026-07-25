from __future__ import annotations

from typing import Any

from auth import AuthError, User
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from ..dependencies import get_app_state, get_current_user
from ..rate_limit import rate_limit_by_ip
from ..state import AppState

router = APIRouter(tags=["auth"])

_auth_rate_limit_dep = Depends(rate_limit_by_ip("auth", limit_attr="auth_rate_limit_per_minute"))


class RegisterRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/auth/register", status_code=201, dependencies=[_auth_rate_limit_dep])
def register(body: RegisterRequest, state: AppState = Depends(get_app_state)) -> dict[str, Any]:
    try:
        user = state.auth_provider.register(body.email, body.password)
    except AuthError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return user.to_public_dict()


@router.post("/auth/login", dependencies=[_auth_rate_limit_dep])
def login(body: LoginRequest, state: AppState = Depends(get_app_state)) -> dict[str, Any]:
    try:
        token = state.auth_provider.authenticate(body.email, body.password)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    user = state.user_store.get_by_id(token.user_id)
    assert user is not None
    return {"token": token.token, "user": user.to_public_dict()}


@router.post("/auth/refresh")
def refresh(
    authorization: str | None = Header(default=None),
    state: AppState = Depends(get_app_state),
) -> dict[str, Any]:
    """Rotates the caller's bearer token: issues a new one and
    invalidates the one supplied in `Authorization`. Deliberately
    doesn't go through `get_current_user` - that dependency only ever
    hands back the resolved `User`, not the raw token string
    `IAuthProvider.refresh_token` needs to invalidate (Phase 8 WP5)."""
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")
    old_token = authorization.removeprefix("Bearer ").strip()
    try:
        new_token = state.auth_provider.refresh_token(old_token)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    user = state.user_store.get_by_id(new_token.user_id)
    assert user is not None
    return {"token": new_token.token, "user": user.to_public_dict()}


@router.get("/users/me")
def get_me(current_user: User = Depends(get_current_user)) -> dict[str, Any]:
    return current_user.to_public_dict()
