import asyncio
import unittest
from datetime import UTC, datetime
from types import SimpleNamespace

from src.core.services.analysis.analysis_processor_service import (
    AnalysisProcessingError,
)
from src.core.services.analysis.analysis_worker_service import AnalysisWorkerService
from src.core.services.analysis.providers.analysis_queue_provider import (
    AnalysisQueueJob,
    AnalysisQueueMessage,
)


class _Queue:
    def __init__(self):
        self.messages = []
        self.acked = 0
        self.failed = 0
        self.requeued = 0
        self.closed = False

    async def receive_async(self, *, timeout_seconds):
        if not self.messages:
            return None
        return self.messages.pop(0)

    async def acknowledge_async(self, message):
        self.acked += 1
        return True

    async def fail_async(self, message, *, error_code):
        self.failed += 1
        return True

    async def requeue_async(self, message, *, delay_seconds, error_code):
        self.requeued += 1
        self.messages.append(
            AnalysisQueueMessage(
                job=message.job,
                receipt=f"receipt-{message.attempt + 1}",
                attempt=message.attempt + 1,
            )
        )
        return True

    async def extend_lease_async(self, message):
        return True

    async def close_async(self):
        self.closed = True


class _Repository:
    def __init__(self):
        self.analysis = SimpleNamespace(
            id="analysis-1",
            analysis_type="COURSE",
            status="pending",
            started_at=None,
        )
        self.cleared = 0

    async def get_aggregate_by_id_async(self, analysis_id):
        if analysis_id != self.analysis.id:
            return None
        return self.analysis

    async def try_claim_processing_async(self, analysis_id):
        if self.analysis.status != "pending":
            return None
        self.analysis.status = "processing"
        self.analysis.started_at = datetime.now(UTC)
        return self.analysis

    async def recover_stale_processing_async(self, analysis_id, *, stale_before):
        return False

    async def get_documents_for_processing_async(self, analysis_id):
        return [{"document_id": "doc-1", "text": "متن", "metadata": {}}]

    async def release_processing_for_retry_async(self, analysis_id):
        if self.analysis.status != "processing":
            return False
        self.analysis.status = "pending"
        self.analysis.started_at = None
        return True

    async def mark_failed_if_active_async(
        self,
        analysis_id,
        *,
        error_code,
        error_message,
    ):
        if self.analysis.status not in {"pending", "processing"}:
            return False
        self.analysis.status = "failed"
        return True

    async def clear_raw_text_async(self, analysis_id):
        self.cleared += 1


class _Processor:
    def __init__(self, repository, failures):
        self.repository = repository
        self.failures = failures
        self.calls = 0

    async def process_claimed_async(self, **kwargs):
        self.calls += 1
        if self.calls <= self.failures:
            raise AnalysisProcessingError()
        self.repository.analysis.status = "completed"


class _Settings:
    concurrency = 1
    maximum_attempts = 2
    retry_initial_delay_seconds = 0.0
    retry_max_delay_seconds = 0.0
    receive_timeout_seconds = 0.01
    poll_interval_seconds = 0.001
    visibility_timeout_seconds = 10.0
    heartbeat_interval_seconds = 1.0
    processing_stale_seconds = 20.0


def _message(attempt=1):
    return AnalysisQueueMessage(
        job=AnalysisQueueJob.create(
            analysis_id="analysis-1",
            analysis_type="COURSE",
        ),
        receipt=f"receipt-{attempt}",
        attempt=attempt,
    )


class AnalysisWorkerServiceTests(unittest.TestCase):
    def test_retryable_failure_requeues_then_succeeds(self) -> None:
        async def run():
            queue = _Queue()
            queue.messages.append(_message())
            repository = _Repository()
            processor = _Processor(repository, failures=1)
            worker = AnalysisWorkerService(
                queue,
                processor,
                repository,
                _Settings(),
            )

            self.assertTrue(await worker.run_once_async())
            self.assertEqual(repository.analysis.status, "pending")
            self.assertEqual(queue.requeued, 1)

            self.assertTrue(await worker.run_once_async())
            self.assertEqual(repository.analysis.status, "completed")
            self.assertEqual(queue.acked, 1)
            self.assertEqual(processor.calls, 2)

        asyncio.run(run())

    def test_retry_exhaustion_fails_and_clears_processing_input(self) -> None:
        async def run():
            queue = _Queue()
            queue.messages.append(_message(attempt=2))
            repository = _Repository()
            processor = _Processor(repository, failures=10)
            worker = AnalysisWorkerService(
                queue,
                processor,
                repository,
                _Settings(),
            )

            await worker.run_once_async()

            self.assertEqual(repository.analysis.status, "failed")
            self.assertEqual(queue.failed, 1)
            self.assertEqual(queue.requeued, 0)
            self.assertEqual(repository.cleared, 1)

        asyncio.run(run())

    def test_completed_duplicate_delivery_is_acknowledged_without_processing(self) -> None:
        async def run():
            queue = _Queue()
            queue.messages.append(_message())
            repository = _Repository()
            repository.analysis.status = "completed"
            processor = _Processor(repository, failures=0)
            worker = AnalysisWorkerService(
                queue,
                processor,
                repository,
                _Settings(),
            )

            await worker.run_once_async()

            self.assertEqual(queue.acked, 1)
            self.assertEqual(processor.calls, 0)

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
