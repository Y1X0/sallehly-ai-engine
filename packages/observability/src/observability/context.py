from __future__ import annotations

import uuid
from contextvars import ContextVar, Token

_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)
_user_id: ContextVar[str | None] = ContextVar("user_id", default=None)
_project_id: ContextVar[str | None] = ContextVar("project_id", default=None)


def new_correlation_id() -> str:
    """A short, URL-safe id - not a UUID's full 36 chars, since this
    shows up in every log line and the `X-Correlation-ID` response
    header; still astronomically unlikely to collide within any single
    process's lifetime."""
    return uuid.uuid4().hex[:16]


def get_correlation_id() -> str | None:
    return _correlation_id.get()


def set_correlation_id(correlation_id: str) -> Token:
    return _correlation_id.set(correlation_id)


def reset_correlation_id(token: Token) -> None:
    _correlation_id.reset(token)


def get_user_id() -> str | None:
    return _user_id.get()


def set_user_id(user_id: str | None) -> Token:
    return _user_id.set(user_id)


def reset_user_id(token: Token) -> None:
    _user_id.reset(token)


def get_project_id() -> str | None:
    return _project_id.get()


def set_project_id(project_id: str | None) -> Token:
    return _project_id.set(project_id)


def reset_project_id(token: Token) -> None:
    _project_id.reset(token)
