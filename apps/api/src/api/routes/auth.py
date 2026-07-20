from __future__ import annotations

from typing import Any

from auth import AuthError, User
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..dependencies import get_app_state, get_current_user
from ..state import AppState

router = APIRouter(tags=["auth"])


class RegisterRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/auth/register", status_code=201)
def register(body: RegisterRequest, state: AppState = Depends(get_app_state)) -> dict[str, Any]:
    try:
        user = state.auth_provider.register(body.email, body.password)
    except AuthError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return user.to_public_dict()


@router.post("/auth/login")
def login(body: LoginRequest, state: AppState = Depends(get_app_state)) -> dict[str, Any]:
    try:
        token = state.auth_provider.authenticate(body.email, body.password)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    user = state.user_store.get_by_id(token.user_id)
    assert user is not None
    return {"token": token.token, "user": user.to_public_dict()}


@router.get("/users/me")
def get_me(current_user: User = Depends(get_current_user)) -> dict[str, Any]:
    return current_user.to_public_dict()
