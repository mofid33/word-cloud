from __future__ import annotations

import re
import secrets
from contextvars import ContextVar
from dataclasses import dataclass


_TRACEPARENT_PATTERN = re.compile(
    r"^00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$"
)

trace_id_context: ContextVar[str | None] = ContextVar("trace_id", default=None)
span_id_context: ContextVar[str | None] = ContextVar("span_id", default=None)


@dataclass(frozen=True)
class TraceContext:
    trace_id: str
    span_id: str
    trace_flags: str = "01"

    @property
    def traceparent(self) -> str:
        return f"00-{self.trace_id}-{self.span_id}-{self.trace_flags}"


def start_server_trace(traceparent: str | None) -> TraceContext:
    parent = _parse_traceparent(traceparent)
    if parent is None:
        trace_id = _nonzero_hex(16)
        trace_flags = "01"
    else:
        trace_id, trace_flags = parent

    return TraceContext(
        trace_id=trace_id,
        span_id=_nonzero_hex(8),
        trace_flags=trace_flags,
    )


def _parse_traceparent(traceparent: str | None) -> tuple[str, str] | None:
    if not traceparent:
        return None
    match = _TRACEPARENT_PATTERN.fullmatch(traceparent.strip().lower())
    if match is None:
        return None
    trace_id, parent_id, trace_flags = match.groups()
    if int(trace_id, 16) == 0 or int(parent_id, 16) == 0:
        return None
    return trace_id, trace_flags


def _nonzero_hex(byte_count: int) -> str:
    while True:
        value = secrets.token_hex(byte_count)
        if int(value, 16) != 0:
            return value
