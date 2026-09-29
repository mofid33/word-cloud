import unittest

from src.core.services.analysis.providers.analysis_queue_provider import (
    AnalysisQueueJob,
)


class AnalysisQueueJobTests(unittest.TestCase):
    def test_round_trip_contains_only_orchestration_metadata(self) -> None:
        job = AnalysisQueueJob.create(
            analysis_id="analysis-1",
            analysis_type="SOLDIER_CONCERN",
        )
        payload = job.to_payload()

        self.assertEqual(
            payload,
            {
                "version": 1,
                "analysis_id": "analysis-1",
                "analysis_type": "SOLDIER_CONCERN",
            },
        )
        self.assertEqual(AnalysisQueueJob.from_payload(payload), job)
        self.assertNotIn("text", repr(payload).lower())
        self.assertNotIn("document", repr(payload).lower())

    def test_rejects_bool_version_unknown_fields_and_invalid_type(self) -> None:
        invalid_payloads = [
            {
                "version": True,
                "analysis_id": "analysis-1",
                "analysis_type": "COURSE",
            },
            {
                "version": 1,
                "analysis_id": "analysis-1",
                "analysis_type": "COURSE",
                "text": "must-not-be-accepted",
            },
            {
                "version": 1,
                "analysis_id": "analysis-1",
                "analysis_type": "UNKNOWN",
            },
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    AnalysisQueueJob.from_payload(payload)


if __name__ == "__main__":
    unittest.main()
