from __future__ import annotations

from fastapi import Request

from .state import AppState


def get_app_state(request: Request) -> AppState:
    return request.app.state.app_state
