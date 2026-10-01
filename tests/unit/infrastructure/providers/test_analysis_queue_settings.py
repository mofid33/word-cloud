import math
import unittest

from src.infrastructure.providers.analysis_queue.analysis_queue_settings import (
    AnalysisQueueSettings,
)


class _Config:
    def __init__(self, overrides=None):
        self.values = {
            "analysis_queue.backend": "postgres",
            "analysis_queue.maximum_attempts": 3,
            "analysis_queue.retry_initial_delay_seconds": 2.0,
            "analysis_queue.retry_max_delay_seconds": 30.0,
            "analysis_queue.receive_timeout_seconds": 2.0,
            "analysis_queue.poll_interval_seconds": 0.25,
            "analysis_queue.visibility_timeout_seconds": 120.0,
            "analysis_queue.heartbeat_interval_seconds": 30.0,
            "analysis_queue.processing_stale_seconds": 300.0,
            "analysis_queue.recovery_interval_seconds": 5.0,
            "analysis_queue.recovery_batch_size": 100,
            "analysis_queue.concurrency": 2,
        }
        self.values.update(overrides or {})

    def require(self, key):
        return self.values[key]


class AnalysisQueueSettingsTests(unittest.TestCase):
    def test_valid_settings_load(self) -> None:
        settings = AnalysisQueueSettings(_Config())
        self.assertEqual(settings.backend, "postgres")
        self.assertEqual(settings.maximum_attempts, 3)
        self.assertEqual(settings.recovery_batch_size, 100)
        self.assertEqual(settings.concurrency, 2)

    def test_bool_is_not_accepted_as_integer(self) -> None:
        with self.assertRaises(ValueError):
            AnalysisQueueSettings(
                _Config({"analysis_queue.maximum_attempts": True})
            )

    def test_nan_inf_and_invalid_ranges_fail_fast(self) -> None:
        invalid = [
            {"analysis_queue.retry_initial_delay_seconds": math.nan},
            {"analysis_queue.retry_max_delay_seconds": math.inf},
            {"analysis_queue.retry_initial_delay_seconds": 31.0},
            {"analysis_queue.poll_interval_seconds": 3.0},
            {"analysis_queue.heartbeat_interval_seconds": 120.0},
            {"analysis_queue.processing_stale_seconds": 60.0},
        ]
        for overrides in invalid:
            with self.subTest(overrides=overrides):
                with self.assertRaises(ValueError):
                    AnalysisQueueSettings(_Config(overrides))


if __name__ == "__main__":
    unittest.main()
