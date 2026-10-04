from __future__ import annotations

import unittest
from unittest.mock import patch

from src.infrastructure.observability.tracing import start_server_trace


class TraceContextTests(unittest.TestCase):
    def test_valid_traceparent_preserves_trace_id_and_flags(self) -> None:
        parent = "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01"
        with patch(
            "src.infrastructure.observability.tracing.secrets.token_hex",
            return_value="1111111111111111",
        ):
            trace = start_server_trace(parent)

        self.assertEqual(
            trace.trace_id,
            "0123456789abcdef0123456789abcdef",
        )
        self.assertEqual(trace.span_id, "1111111111111111")
        self.assertEqual(
            trace.traceparent,
            "00-0123456789abcdef0123456789abcdef-1111111111111111-01",
        )

    def test_invalid_or_zero_traceparent_creates_new_context(self) -> None:
        values = iter(
            [
                "22222222222222222222222222222222",
                "3333333333333333",
            ]
        )
        with patch(
            "src.infrastructure.observability.tracing.secrets.token_hex",
            side_effect=lambda _byte_count: next(values),
        ):
            trace = start_server_trace(
                "00-00000000000000000000000000000000-0123456789abcdef-01"
            )

        self.assertEqual(
            trace.trace_id,
            "22222222222222222222222222222222",
        )
        self.assertEqual(trace.span_id, "3333333333333333")
        self.assertEqual(trace.trace_flags, "01")


if __name__ == "__main__":
    unittest.main()
