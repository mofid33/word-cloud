from __future__ import annotations

import logging
import unittest

from src.infrastructure.observability.logging_config import JsonFormatter, request_id_context
from src.infrastructure.observability.tracing import span_id_context, trace_id_context


class LoggingPrivacyTests(unittest.TestCase):
    def test_formatter_does_not_emit_message_or_exception_text(self) -> None:
        secret = "SOLDIER-RAW-TEXT-MARKER"
        try:
            raise RuntimeError(secret)
        except RuntimeError:
            exc_info = __import__("sys").exc_info()

        record = logging.LogRecord(
            name="privacy",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg=secret,
            args=(),
            exc_info=exc_info,
        )
        record.event = "analysis_failed"
        rendered = JsonFormatter().format(record)
        self.assertNotIn(secret, rendered)
        self.assertIn('"event":"analysis_failed"', rendered)
        self.assertIn('"error_type":"RuntimeError"', rendered)

    def test_trace_context_emits_only_safe_identifiers(self) -> None:
        trace_token = trace_id_context.set(
            "0123456789abcdef0123456789abcdef"
        )
        span_token = span_id_context.set("0123456789abcdef")
        try:
            record = logging.LogRecord(
                "privacy",
                logging.INFO,
                __file__,
                1,
                "ignored",
                (),
                None,
            )
            record.event = "http_request_completed"
            rendered = JsonFormatter().format(record)
            self.assertIn(
                '"trace_id":"0123456789abcdef0123456789abcdef"',
                rendered,
            )
            self.assertIn('"span_id":"0123456789abcdef"', rendered)
        finally:
            span_id_context.reset(span_token)
            trace_id_context.reset(trace_token)

    def test_request_id_is_safe_context_only(self) -> None:
        token = request_id_context.set("request-123")
        try:
            record = logging.LogRecord("privacy", logging.INFO, __file__, 1, "ignored", (), None)
            record.event = "http_request_completed"
            rendered = JsonFormatter().format(record)
            self.assertIn('"request_id":"request-123"', rendered)
        finally:
            request_id_context.reset(token)


if __name__ == "__main__":
    unittest.main()
