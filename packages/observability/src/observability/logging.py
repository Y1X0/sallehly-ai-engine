from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from . import context

_RESERVED_RECORD_ATTRS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()) | {
    "message",
    "asctime",
}

_configured_service_name = "sallehly"


class _ContextFilter(logging.Filter):
    """Injects the request-scoped `correlation_id`/`user_id`/`project_id`
    contextvars (`observability.context`) into every `LogRecord` that
    passes through - a `logging.Filter` is the standard stdlib mechanism
    for attaching cross-cutting fields without every call site having to
    pass them explicitly."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "correlation_id"):
            record.correlation_id = context.get_correlation_id()
        if not hasattr(record, "user_id"):
            record.user_id = context.get_user_id()
        if not hasattr(record, "project_id"):
            record.project_id = context.get_project_id()
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line to stdout - the format every log
    aggregator (CloudWatch, Datadog, Loki, ...) expects without a
    separate parser. Any `extra={...}` fields passed to a log call
    (`logger.info("...", extra={"job_id": job_id})`) are merged directly
    into the JSON object, not nested - so `job_id` shows up as a real
    top-level, queryable field.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": _configured_service_name,
        }
        correlation_id = getattr(record, "correlation_id", None)
        if correlation_id is not None:
            payload["correlation_id"] = correlation_id
        user_id = getattr(record, "user_id", None)
        if user_id is not None:
            payload["user_id"] = user_id
        project_id = getattr(record, "project_id", None)
        if project_id is not None:
            payload["project_id"] = project_id

        for key, value in record.__dict__.items():
            if key not in _RESERVED_RECORD_ATTRS and key not in payload:
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def configure_logging(service_name: str = "sallehly", level: str = "INFO") -> None:
    """Wires the root logger to emit one JSON line per record to stdout.
    Idempotent - safe to call more than once (every test module that
    exercises `apps/api`'s lifespan does), clears any handlers a
    previous call installed rather than stacking duplicates."""
    global _configured_service_name
    _configured_service_name = service_name

    root = logging.getLogger()
    root.setLevel(level.upper())
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(_ContextFilter())
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Returns a plain stdlib `logging.Logger` - every field this module
    adds (JSON shape, correlation id, ...) comes from `configure_logging`'s
    handler/formatter/filter, not from wrapping the logger itself, so
    normal `logger.info(...)`/`logger.warning(...)`/`logger.exception(...)`
    calls need no special API to learn."""
    return logging.getLogger(name)
