from __future__ import annotations

import asyncio
import inspect
import unittest
from unittest.mock import patch

from src.core.services.health.health_service import HealthService
from src.host import worker_health
from src.infrastructure.context.sql_db.psql_dbcontext import PsqlDbContext
from src.infrastructure.providers.analysis_queue.redis_analysis_transient_payload_store import (
    RedisAnalysisTransientPayloadStore,
)


class _Health:
    async def readiness_async(self):
        return True, {"status": "ready"}


class _Db:
    def __init__(self):
        self.closed = False

    async def dispose_async(self):
        self.closed = True


class _Redis:
    def __init__(self):
        self.closed = False

    async def close_async(self):
        self.closed = True


class WorkerHealthProbeTests(unittest.TestCase):
    def test_probe_does_not_bootstrap_full_discovery(self) -> None:
        source = inspect.getsource(worker_health)
        self.assertNotIn("bootstrap_di", source)

    def test_probe_checks_readiness_and_closes_resources(self) -> None:
        health = _Health()
        db = _Db()
        redis_store = _Redis()

        def fake_resolve(dependency_type):
            if dependency_type is HealthService:
                return health
            if dependency_type is PsqlDbContext:
                return db
            if dependency_type is RedisAnalysisTransientPayloadStore:
                return redis_store
            raise AssertionError(dependency_type)

        with patch.object(worker_health, "resolve", side_effect=fake_resolve):
            result = asyncio.run(worker_health._main_async())

        self.assertEqual(result, 0)
        self.assertTrue(db.closed)
        self.assertTrue(redis_store.closed)


if __name__ == "__main__":
    unittest.main()
