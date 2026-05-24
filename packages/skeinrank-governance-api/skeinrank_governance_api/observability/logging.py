"""Logging setup for the SkeinRank governance API."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from ..config import GovernanceApiConfig
from .context import get_request_id

_OBSERVABILITY_HANDLER_NAME = "skeinrank_observability"

_RESERVED_LOG_RECORD_FIELDS = frozenset(
    {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "message",
    }
)


class JsonLogFormatter(logging.Formatter):
    """Small dependency-free JSON log formatter."""

    def __init__(self, *, service_name: str, service_version: str) -> None:
        super().__init__()
        self.service_name = service_name
        self.service_version = service_version

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
            "service": {
                "name": self.service_name,
                "version": self.service_version,
            },
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        request_id = getattr(record, "request_id", None) or get_request_id()
        if request_id:
            payload["request_id"] = request_id
        for key, value in sorted(record.__dict__.items()):
            if key in _RESERVED_LOG_RECORD_FIELDS or key.startswith("_"):
                continue
            if key in payload or key == "request_id":
                continue
            payload[key] = _json_safe(value)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def configure_logging(config: GovernanceApiConfig) -> None:
    """Configure process logging according to API observability settings."""

    if not config.observability_enabled:
        return

    root_logger = logging.getLogger()
    root_logger.setLevel(_log_level(config.log_level))
    handler = _find_observability_handler(root_logger)
    if handler is None:
        handler = logging.StreamHandler(sys.stdout)
        handler.name = _OBSERVABILITY_HANDLER_NAME
        root_logger.addHandler(handler)
    handler.setLevel(_log_level(config.log_level))
    if config.log_format == "json":
        handler.setFormatter(
            JsonLogFormatter(
                service_name=config.service_name,
                service_version=config.service_version,
            )
        )
    else:
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S%z",
            )
        )


def structured_log(
    logger: logging.Logger,
    level: int,
    message: str,
    *,
    event: str,
    outcome: str | None = None,
    exc_info: bool | tuple[Any, Any, Any] | None = None,
    **fields: Any,
) -> None:
    """Emit a structured log event with collision-safe extra fields.

    ``logging`` rejects ``extra`` keys that collide with LogRecord attributes.
    This helper keeps route/middleware code simple by normalizing those keys and
    by applying the same JSON-safety rules used by :class:`JsonLogFormatter`.
    """

    logger.log(
        level,
        message,
        extra=structured_log_extra(event=event, outcome=outcome, **fields),
        exc_info=exc_info,
    )


def structured_log_extra(
    *,
    event: str,
    outcome: str | None = None,
    **fields: Any,
) -> dict[str, Any]:
    """Build a collision-safe ``extra`` payload for structured logs."""

    payload: dict[str, Any] = {"event": event}
    if outcome:
        payload["outcome"] = outcome
    for key, value in fields.items():
        normalized_key = _safe_extra_key(str(key))
        payload[normalized_key] = _json_safe(value)
    return payload


def _safe_extra_key(key: str) -> str:
    if key in _RESERVED_LOG_RECORD_FIELDS or key.startswith("_"):
        return f"field_{key.lstrip('_')}"
    return key


def _find_observability_handler(logger: logging.Logger) -> logging.Handler | None:
    for handler in logger.handlers:
        if getattr(handler, "name", None) == _OBSERVABILITY_HANDLER_NAME:
            return handler
    return None


def _log_level(value: str) -> int:
    return getattr(logging, value.upper(), logging.INFO)


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return str(value)
