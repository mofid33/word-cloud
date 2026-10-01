from __future__ import annotations

import unittest

from src.core.services.health.health_service import HealthService


class _Result:
    async def execute(self, _query):
        return None


class _SessionContext:
    async def __aenter__(self):
        return _Result()

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Db:
    def session(self):
        return _SessionContext()


class _Redis:
    async def ping_async(self):
        return True


class _Metrics:
    def __init__(self):
        self.ready = None

    def set_readiness(self, value):
        self.ready = value


class HealthServiceTests(unittest.TestCase):
    def test_readiness_requires_postgres_and_transient_redis(self) -> None:
        async def run():
            metrics = _Metrics()
            service = HealthService(_Db(), _Redis(), metrics)
            ready, payload = await service.readiness_async()
            self.assertTrue(ready)
            self.assertEqual(payload["status"], "ready")
            self.assertEqual(payload["checks"], {"postgres": True, "redis_transient": True})
            self.assertTrue(metrics.ready)

        __import__("asyncio").run(run())


if __name__ == "__main__":
    unittest.main()
