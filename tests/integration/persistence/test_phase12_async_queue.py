from __future__ import annotations

import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine import make_url

from src.application.analysis.analysis_controller import AnalysisController
from src.core.services.analysis.analysis_execution_policy_service import (
    AnalysisExecutionPolicyService,
)
from src.core.services.analysis.analysis_processor_service import AnalysisProcessorService
from src.core.services.analysis.analysis_service import AnalysisService
from src.core.services.analysis.analysis_worker_service import AnalysisWorkerService
from src.core.services.analysis.providers.analysis_queue_provider import AnalysisQueueJob
from src.infrastructure.context.sql_db.psql_dbcontext import Base, PsqlDbContext
from src.infrastructure.providers.analysis_queue.postgres_analysis_queue_provider import (
    PostgresAnalysisQueueProvider,
)
from src.infrastructure.repositories.analysis.analysis_queue_repository import (
    AnalysisQueueRepository,
)
from src.infrastructure.repositories.analysis.word_cloud_analysis_repository import (
    WordCloudAnalysisRepository,
)


class _Config:
    def __init__(self, url):
        self._url = url

    def require(self, key):
        if key != "database.url":
            raise KeyError(key)
        return self._url


class _Vault:
    enabled = False


class _TransientStore:
    def __init__(self):
        self.payloads = {}

    async def put_async(self, analysis_id, documents):
        self.payloads[analysis_id] = list(documents)

    async def get_async(self, analysis_id):
        return self.payloads.get(analysis_id)

    async def touch_async(self, analysis_id):
        return analysis_id in self.payloads

    async def delete_async(self, analysis_id):
        self.payloads.pop(analysis_id, None)

    async def close_async(self):
        return None


class _Settings:
    poll_interval_seconds = 0.01
    visibility_timeout_seconds = 30.0


class _ShortLeaseSettings:
    poll_interval_seconds = 0.005
    visibility_timeout_seconds = 0.05


class _WorkerSettings(_Settings):
    concurrency = 1
    maximum_attempts = 3
    retry_initial_delay_seconds = 0.0
    retry_max_delay_seconds = 0.0
    receive_timeout_seconds = 0.05
    heartbeat_interval_seconds = 5.0
    processing_stale_seconds = 60.0
    recovery_interval_seconds = 60.0
    recovery_batch_size = 100


class _CrashRecoveryWorkerSettings(_WorkerSettings):
    processing_stale_seconds = 0.05


class _PolicyConfig:
    def __init__(self):
        self.values = {
            "analysis.limits.max_documents_per_analysis": 5000,
            "analysis.limits.max_characters_per_document": 500000,
            "analysis.limits.max_total_characters_per_analysis": 10000000,
            "analysis.sync_threshold.max_documents": 20,
            "analysis.sync_threshold.max_total_characters": 100000,
        }

    def require(self, key):
        return self.values[key]


class _ProfileService:
    async def analyze_async(self, documents):
        return SimpleNamespace(
            keywords=(),
            topics=(),
            metrics={"document_count": len(documents)},
            profile_result={"profile": "test"},
            model_version="phase12-test-model",
            scoring_version="phase12-test-score",
        )


def _test_database_url():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        return None
    database_name = make_url(url).database or ""
    if "test" not in database_name.lower():
        raise RuntimeError(
            "TEST_DATABASE_URL must point to a database whose name contains 'test'"
        )
    return url


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
class Phase12AsyncQueueIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        url = _test_database_url()
        assert url is not None
        with patch.dict(os.environ, {"DATABASE_URL": url}, clear=False):
            self.db_context = PsqlDbContext(_Config(url), _Vault())
        self.repository = WordCloudAnalysisRepository(self.db_context)
        self.queue_repository = AnalysisQueueRepository(self.db_context)
        self.transient_store = _TransientStore()
        self.queue = PostgresAnalysisQueueProvider(
            self.queue_repository,
            _Settings(),
            self.transient_store,
        )
        async with self.db_context.engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)

    async def asyncTearDown(self):
        async with self.db_context.engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        await self.db_context.dispose_async()

    async def _create_analysis(self):
        return await self.repository.create_pending_async(
            analysis_type="COURSE",
            execution_mode="async",
            documents=[
                {
                    "document_id": "doc-1",
                    "text": "متن برای پردازش",
                    "metadata": {"section": "1"},
                }
            ],
            persist_raw_text=True,
        )

    def _processor(self):
        profile = _ProfileService()
        return AnalysisProcessorService(
            profile,
            profile,
            profile,
            self.repository,
        )

    async def test_async_api_create_queue_worker_completed_end_to_end(self):
        processor = self._processor()
        policy = AnalysisExecutionPolicyService(_PolicyConfig())
        service = AnalysisService(
            policy,
            processor,
            self.repository,
            self.queue,
        )
        worker = AnalysisWorkerService(
            self.queue,
            processor,
            self.repository,
            _WorkerSettings(),
        )
        controller = AnalysisController(service)
        app = FastAPI()
        app.include_router(
            controller.api(),
            prefix="/api/v1/analysis",
        )

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            created = await client.post(
                "/api/v1/analysis",
                json={
                    "analysis_type": "COURSE",
                    "execution_mode": "async",
                    "documents": [
                        {
                            "document_id": "course-1",
                            "text": "پردازش ناهمگام متن فارسی",
                            "metadata": {"section": "1"},
                        }
                    ],
                },
            )
            self.assertEqual(created.status_code, 201)
            body = created.json()
            self.assertEqual(body["status"], "pending")
            analysis_id = body["analysis_id"]

            self.assertTrue(await worker.run_once_async())

            status_response = await client.get(
                f"/api/v1/analysis/{analysis_id}"
            )
            self.assertEqual(status_response.status_code, 200)
            self.assertEqual(status_response.json()["status"], "completed")

        completed = await self.repository.get_aggregate_by_id_async(analysis_id)
        self.assertEqual(completed.status, "completed")
        self.assertEqual(completed.model_version, "phase12-test-model")
        self.assertEqual(completed.scoring_version, "phase12-test-score")
        self.assertIsNone(completed.documents[0].raw_text)

    async def test_enqueue_receive_ack_uses_identifier_only_payload(self):
        analysis = await self._create_analysis()
        job = AnalysisQueueJob.create(
            analysis_id=analysis.id,
            analysis_type="COURSE",
        )
        await self.queue.enqueue_async(analysis.id, job.to_payload())

        message = await self.queue.receive_async(timeout_seconds=0.2)
        self.assertIsNotNone(message)
        assert message is not None
        self.assertEqual(message.job, job)
        self.assertEqual(message.attempt, 1)
        self.assertNotIn("متن برای پردازش", repr(message.job.to_payload()))
        self.assertTrue(await self.queue.acknowledge_async(message))
        self.assertIsNone(
            await self.queue.receive_async(timeout_seconds=0.05)
        )

    async def test_requeue_increments_delivery_attempt(self):
        analysis = await self._create_analysis()
        job = AnalysisQueueJob.create(
            analysis_id=analysis.id,
            analysis_type="COURSE",
        )
        await self.queue.enqueue_async(analysis.id, job.to_payload())

        first = await self.queue.receive_async(timeout_seconds=0.2)
        assert first is not None
        self.assertTrue(
            await self.queue.requeue_async(
                first,
                delay_seconds=0.0,
                error_code="analysis_processing_failed",
            )
        )
        second = await self.queue.receive_async(timeout_seconds=0.2)
        assert second is not None
        self.assertEqual(second.attempt, 2)
        await self.queue.acknowledge_async(second)

    async def test_concurrent_workers_receive_one_effective_delivery(self):
        analysis = await self._create_analysis()
        job = AnalysisQueueJob.create(
            analysis_id=analysis.id,
            analysis_type="COURSE",
        )
        await self.queue.enqueue_async(analysis.id, job.to_payload())

        first, second = await asyncio.gather(
            self.queue.receive_async(timeout_seconds=0.1),
            self.queue.receive_async(timeout_seconds=0.1),
        )
        delivered = [item for item in (first, second) if item is not None]
        self.assertEqual(len(delivered), 1)
        await self.queue.acknowledge_async(delivered[0])

    async def test_atomic_processing_claim_allows_exactly_one_winner(self):
        analysis = await self._create_analysis()

        first, second = await asyncio.gather(
            self.repository.try_claim_processing_async(analysis.id),
            self.repository.try_claim_processing_async(analysis.id),
        )

        winners = [item for item in (first, second) if item is not None]
        self.assertEqual(len(winners), 1)
        current = await self.repository.get_aggregate_by_id_async(analysis.id)
        self.assertEqual(current.status, "processing")

    async def test_processing_documents_are_cleared_after_failure(self):
        analysis = await self._create_analysis()
        documents = await self.repository.get_documents_for_processing_async(
            analysis.id
        )
        self.assertEqual(documents[0]["text"], "متن برای پردازش")

        await self.repository.mark_failed_if_active_async(
            analysis.id,
            error_code="analysis_processing_failed",
            error_message="Analysis processing failed",
        )
        failed = await self.repository.get_aggregate_by_id_async(analysis.id)
        self.assertEqual(failed.status, "failed")
        self.assertIsNone(failed.documents[0].raw_text)

    async def test_orphaned_pending_analysis_is_recovered_into_queue(self):
        analysis = await self._create_analysis()

        recovered = await self.queue.recover_orphaned_async(limit=10)

        self.assertEqual(recovered, 1)
        message = await self.queue.receive_async(timeout_seconds=0.2)
        self.assertIsNotNone(message)
        assert message is not None
        self.assertEqual(message.job.analysis_id, analysis.id)
        self.assertEqual(message.job.analysis_type, "COURSE")
        await self.queue.acknowledge_async(message)

    async def test_expired_lease_and_stale_processing_are_recovered(self):
        analysis = await self._create_analysis()
        queue = PostgresAnalysisQueueProvider(
            self.queue_repository,
            _ShortLeaseSettings(),
            self.transient_store,
        )
        job = AnalysisQueueJob.create(
            analysis_id=analysis.id,
            analysis_type="COURSE",
        )
        await queue.enqueue_async(analysis.id, job.to_payload())
        first = await queue.receive_async(timeout_seconds=0.2)
        self.assertIsNotNone(first)
        await self.repository.try_claim_processing_async(analysis.id)

        await asyncio.sleep(0.08)

        worker = AnalysisWorkerService(
            queue,
            self._processor(),
            self.repository,
            _CrashRecoveryWorkerSettings(),
        )
        self.assertTrue(await worker.run_once_async())

        completed = await self.repository.get_aggregate_by_id_async(analysis.id)
        self.assertEqual(completed.status, "completed")
        self.assertIsNone(
            await queue.receive_async(timeout_seconds=0.05)
        )


if __name__ == "__main__":
    unittest.main()
