from __future__ import annotations

import logging
import unittest

from tests.evaluation.phase10_test_support import build_profile_services


class _CaptureHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.messages = []

    def emit(self, record):
        self.messages.append(self.format(record))


class SoldierPrivacyRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.service = build_profile_services()["SOLDIER_CONCERN"]

    async def test_raw_concern_text_is_absent_from_logs_results_metrics_and_profile_metadata(self):
        raw = "SOLDIER-PRIVATE-RAW-TEXT-9f4196d1"
        handler = _CaptureHandler()
        root = logging.getLogger()
        root.addHandler(handler)
        try:
            result = await self.service.analyze_async([
                {
                    "document_id": "concern-1",
                    "text": raw,
                    "metadata": {},
                }
            ])
        finally:
            root.removeHandler(handler)

        self.assertNotIn(raw, "\n".join(handler.messages))
        self.assertNotIn(raw, repr(result.metrics))
        self.assertNotIn(raw, repr(result.profile_result))
        self.assertNotIn(raw, repr(result))

    async def test_user_controlled_raw_text_is_not_echoed_by_validation_errors(self):
        raw = "SOLDIER-SECRET-MALFORMED-0d49"
        with self.assertRaises(ValueError) as context:
            await self.service.analyze_async([
                {
                    "document_id": " concern-1 ",
                    "text": raw,
                    "metadata": [],
                }
            ])
        self.assertNotIn(raw, str(context.exception))

    async def test_normalized_duplicate_document_ids_are_rejected_without_echo(self):
        raw = "SOLDIER-PRIVATE-DUPLICATE-0ba2"
        with self.assertRaises(ValueError) as context:
            await self.service.analyze_async([
                {"document_id": "same", "text": raw, "metadata": {}},
                {"document_id": " same ", "text": "متن دوم", "metadata": {}},
            ])
        self.assertNotIn(raw, str(context.exception))


if __name__ == "__main__":
    unittest.main()
