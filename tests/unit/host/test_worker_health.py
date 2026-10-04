from __future__ import annotations

import inspect
import unittest
from unittest.mock import MagicMock, patch

from src.host import worker_health


class _Response:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class WorkerHealthProbeTests(unittest.TestCase):
    def test_probe_uses_only_stdlib_runtime_dependencies(self) -> None:
        source = inspect.getsource(worker_health)
        self.assertNotIn("bootstrap_di", source)
        self.assertNotIn("sqlalchemy", source)
        self.assertNotIn("redis", source)
        self.assertNotIn("src.core", source)
        self.assertNotIn("src.infrastructure", source)

    def test_probe_requires_worker_process_and_api_readiness(self) -> None:
        with (
            patch.object(worker_health.os, "kill") as kill,
            patch.object(
                worker_health,
                "urlopen",
                return_value=_Response(),
            ) as urlopen_mock,
        ):
            self.assertTrue(worker_health._is_healthy())

        kill.assert_called_once_with(1, 0)
        request = urlopen_mock.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "http://api:5000/api/v1/health/ready",
        )
        self.assertEqual(request.get_header("Host"), "localhost")
        self.assertEqual(
            urlopen_mock.call_args.kwargs["timeout"],
            5.0,
        )

    def test_probe_is_unhealthy_when_worker_process_is_missing(self) -> None:
        with (
            patch.object(
                worker_health.os,
                "kill",
                side_effect=ProcessLookupError(),
            ),
            patch.object(worker_health, "urlopen") as urlopen_mock,
        ):
            self.assertFalse(worker_health._is_healthy())

        urlopen_mock.assert_not_called()

    def test_probe_is_unhealthy_when_api_readiness_is_unavailable(self) -> None:
        with (
            patch.object(worker_health.os, "kill"),
            patch.object(
                worker_health,
                "urlopen",
                side_effect=worker_health.URLError("unavailable"),
            ),
        ):
            self.assertFalse(worker_health._is_healthy())


if __name__ == "__main__":
    unittest.main()
