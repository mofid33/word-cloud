from __future__ import annotations

import json
import logging
import os
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any


request_id_context: ContextVar[str | None] = ContextVar("request_id", default=None)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "severity": record.levelname,
            "event": getattr(record, "event", "log_event"),
        }
        request_id = request_id_context.get()
        if request_id:
            payload["request_id"] = request_id
        for key in ("method", "route", "status_code", "duration_ms", "analysis_id", "profile", "execution_mode", "error_code"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["error_type"] = record.exc_info[0].__name__
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging(level: str | None = None) -> None:
    configured_level = (level or os.getenv("LOG_LEVEL", "INFO")).strip().upper()
    if configured_level not in logging._nameToLevel:
        raise ValueError("LOG_LEVEL is invalid")
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(configured_level)
