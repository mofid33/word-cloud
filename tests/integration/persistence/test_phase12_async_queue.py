from __future__ import annotations

import asyncio
import os
import unittest
from unittest.mock import patch

from sqlalchemy.engine import make_url

from src.core.services.analysis.providers.analysis_queue_provider import AnalysisQueueJob
from src.infrastructure.context.sql_db.psql_dbcontext import Base, PsqlDbContext
from src.infrastructure.models.analysis_queue_job import AnalysisQueueJobModel
from src.infrastructure.providers.analysis_queue.postgres_analysis_queue_provider import (
    PostgresAnalysisQueueProvider,
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


class _Settings:
    poll_interval_seconds = 0.01
    visibility_timeout_seconds = 30.0


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
        self.queue = PostgresAnalysisQueueProvider(
            self.db_context,
            _Settings(),
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
        await self.repository.clear_raw_text_async(analysis.id)
        failed = await self.repository.get_aggregate_by_id_async(analysis.id)
        self.assertEqual(failed.status, "failed")
        self.assertIsNone(failed.documents[0].raw_text)


if __name__ == "__main__":
    unittest.main()
