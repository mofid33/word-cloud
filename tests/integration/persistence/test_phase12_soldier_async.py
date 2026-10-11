from __future__ import annotations

import os
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.engine import make_url

from src.core.services.analysis.analysis_execution_policy_service import (
    AnalysisExecutionPolicyService,
)
from src.core.services.analysis.analysis_processor_service import AnalysisProcessorService
from src.core.services.analysis.analysis_service import AnalysisService
from src.core.services.analysis.analysis_worker_service import AnalysisWorkerService
from src.infrastructure.context.sql_db.psql_dbcontext import Base, PsqlDbContext
from src.infrastructure.models.analysis_queue_job import AnalysisQueueJobModel
from src.infrastructure.providers.analysis_queue.postgres_analysis_queue_provider import (
    PostgresAnalysisQueueProvider,
)
from src.infrastructure.providers.analysis_queue.redis_analysis_transient_payload_store import (
    RedisAnalysisTransientPayloadStore,
)
from src.infrastructure.repositories.analysis.analysis_queue_repository import (
    AnalysisQueueRepository,
)
from src.infrastructure.repositories.analysis.word_cloud_analysis_repository import (
    WordCloudAnalysisRepository,
)


class _DatabaseConfig:
    def __init__(self, url):
        self._url = url

    def require(self, key):
        if key == "database.url":
            return self._url
        raise KeyError(key)

    def get(self, key, default=None):
        return default


class _TransientConfig:
    def __init__(self, url, key_prefix):
        self.values = {
            "analysis_queue.transient_payload.backend": "redis",
            "analysis_queue.transient_payload.url": url,
            "analysis_queue.transient_payload.ttl_seconds": 3600,
            "analysis_queue.transient_payload.socket_timeout_seconds": 5.0,
            "analysis_queue.transient_payload.key_prefix": key_prefix,
        }

    def require(self, key):
        return self.values[key]

    def get(self, key, default=None):
        return self.values.get(key, default)


class _Vault:
    enabled = False


class _QueueSettings:
    poll_interval_seconds = 0.01
    visibility_timeout_seconds = 30.0


class _WorkerSettings:
    concurrency = 1
    maximum_attempts = 3
    retry_initial_delay_seconds = 0.0
    retry_max_delay_seconds = 0.0
    receive_timeout_seconds = 0.05
    poll_interval_seconds = 0.01
    visibility_timeout_seconds = 30.0
    heartbeat_interval_seconds = 5.0
    processing_stale_seconds = 60.0
    recovery_interval_seconds = 60.0
    recovery_batch_size = 100


class _PolicyConfig:
    values = {
        "analysis.limits.max_documents_per_analysis": 5000,
        "analysis.limits.max_characters_per_document": 500000,
        "analysis.limits.max_total_characters_per_analysis": 10000000,
        "analysis.sync_threshold.max_documents": 20,
        "analysis.sync_threshold.max_total_characters": 100000,
        "analysis.sync_threshold.max_estimated_candidates": 1500,
        "analysis.sync_threshold.course_max_total_characters": 8000,
        "analysis.sync_threshold.course_max_estimated_candidates": 1200,
        "analysis.sync_threshold.processing_timeout_seconds": 240,
    }

    def require(self, key):
        return self.values[key]


class _Profile:
    async def analyze_async(self, documents):
        return SimpleNamespace(
            keywords=(),
            topics=(),
            metrics={"document_count": len(documents)},
            profile_result={"profile": "soldier-test"},
            model_version="phase12-soldier-test-model",
            scoring_version="phase12-soldier-test-score",
        )


def _test_database_url():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        return None
    if "test" not in (make_url(url).database or "").lower():
        raise RuntimeError(
            "TEST_DATABASE_URL must point to a database whose name contains 'test'"
        )
    return url


_REQUIRED = bool(
    os.getenv("TEST_DATABASE_URL")
    and os.getenv("TEST_TRANSIENT_PAYLOAD_REDIS_URL")
)


@unittest.skipUnless(
    _REQUIRED,
    "TEST_DATABASE_URL and TEST_TRANSIENT_PAYLOAD_REDIS_URL are required",
)
class Phase12SoldierAsyncIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        database_url = _test_database_url()
        redis_url = os.environ["TEST_TRANSIENT_PAYLOAD_REDIS_URL"]
        assert database_url is not None

        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": database_url,
                "TRANSIENT_PAYLOAD_REDIS_URL": redis_url,
            },
            clear=False,
        ):
            self.db_context = PsqlDbContext(
                _DatabaseConfig(database_url),
                _Vault(),
            )
            self.transient_store = RedisAnalysisTransientPayloadStore(
                _TransientConfig(
                    redis_url,
                    f"test:phase12:{uuid4()}:",
                ),
                _Vault(),
            )

        async with self.db_context.engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)

        self.analysis_repository = WordCloudAnalysisRepository(self.db_context)
        self.queue_repository = AnalysisQueueRepository(self.db_context)
        self.queue = PostgresAnalysisQueueProvider(
            self.queue_repository,
            _QueueSettings(),
            self.transient_store,
        )

    async def asyncTearDown(self):
        await self.queue.close_async()
        async with self.db_context.engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        await self.db_context.dispose_async()

    async def test_soldier_orphan_dispatch_recovers_after_api_crash_window(self):
        analysis_id = str(uuid4())
        marker = "SOLDIER-ORPHAN-RECOVERY-MARKER"
        documents = [
            {
                "document_id": "private-orphan-id",
                "text": marker,
                "metadata": {},
            }
        ]
        await self.transient_store.put_async(analysis_id, documents)
        await self.analysis_repository.create_pending_async(
            analysis_type="SOLDIER_CONCERN",
            execution_mode="async",
            documents=documents,
            persist_raw_text=False,
            analysis_id=analysis_id,
        )

        recovered = await self.queue.recover_orphaned_async(limit=10)
        self.assertEqual(recovered, 1)

        profile = _Profile()
        processor = AnalysisProcessorService(
            profile,
            profile,
            profile,
            self.analysis_repository,
        )
        worker = AnalysisWorkerService(
            self.queue,
            processor,
            self.analysis_repository,
            _WorkerSettings(),
        )
        self.assertTrue(await worker.run_once_async())

        completed = await self.analysis_repository.get_aggregate_by_id_async(
            analysis_id
        )
        self.assertEqual(completed.status, "completed")
        self.assertIsNone(completed.documents[0].raw_text)
        self.assertIsNone(await self.transient_store.get_async(analysis_id))

    async def test_soldier_async_never_persists_raw_text_or_durable_payload(self):
        marker = "SOLDIER-RAW-SECRET-MARKER"
        profile = _Profile()
        processor = AnalysisProcessorService(
            profile,
            profile,
            profile,
            self.analysis_repository,
        )
        service = AnalysisService(
            AnalysisExecutionPolicyService(_PolicyConfig()),
            processor,
            self.analysis_repository,
            self.queue,
        )

        created = await service.create_async(
            analysis_type="SOLDIER_CONCERN",
            execution_mode="async",
            documents=[
                {
                    "document_id": "concern-sensitive-id",
                    "text": marker,
                    "metadata": {"source": "private"},
                }
            ],
            reference="must-not-persist",
            options={"private": marker},
        )
        self.assertEqual(created.status, "pending")

        aggregate = await self.analysis_repository.get_aggregate_by_id_async(
            created.analysis_id
        )
        self.assertIsNone(aggregate.reference)
        self.assertEqual(aggregate.options, {})
        self.assertIsNone(aggregate.documents[0].raw_text)
        self.assertTrue(aggregate.documents[0].document_id.startswith("sha256:"))
        self.assertEqual(aggregate.documents[0].metadata_json, {})

        async with self.db_context.session() as session:
            payload = (
                await session.execute(
                    select(AnalysisQueueJobModel.payload).where(
                        AnalysisQueueJobModel.analysis_id == created.analysis_id
                    )
                )
            ).scalar_one()
        self.assertNotIn(marker, repr(payload))
        self.assertNotIn("concern-sensitive-id", repr(payload))

        transient_documents = await self.transient_store.get_async(
            created.analysis_id
        )
        self.assertEqual(transient_documents[0]["text"], marker)

        worker = AnalysisWorkerService(
            self.queue,
            processor,
            self.analysis_repository,
            _WorkerSettings(),
        )
        self.assertTrue(await worker.run_once_async())

        completed = await self.analysis_repository.get_aggregate_by_id_async(
            created.analysis_id
        )
        self.assertEqual(completed.status, "completed")
        self.assertIsNone(completed.documents[0].raw_text)
        self.assertIsNone(
            await self.transient_store.get_async(created.analysis_id)
        )


if __name__ == "__main__":
    unittest.main()
