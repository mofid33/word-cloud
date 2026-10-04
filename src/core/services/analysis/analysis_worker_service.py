from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from time import monotonic

from src.core.services.analysis.analysis_processor_service import (
    AnalysisProcessingError,
    AnalysisProcessorService,
)
from src.core.services.analysis.providers.analysis_queue_provider import (
    AnalysisQueueInvalidMessageError,
    AnalysisQueueMessage,
    AnalysisQueueProvider,
)
from src.infrastructure.di.inject import inject
from src.infrastructure.providers.analysis_queue.analysis_queue_settings import (
    AnalysisQueueSettings,
)
from src.infrastructure.repositories.analysis.word_cloud_analysis_repository import (
    WordCloudAnalysisRepository,
)


_logger = logging.getLogger("word_cloud.worker")


@inject
class AnalysisWorkerService:
    def __init__(
        self,
        queue_provider: AnalysisQueueProvider,
        analysis_processor_service: AnalysisProcessorService,
        analysis_repository: WordCloudAnalysisRepository,
        settings: AnalysisQueueSettings,
    ):
        self._queue = queue_provider
        self._processor = analysis_processor_service
        self._repository = analysis_repository
        self._settings = settings
        self._shutdown = asyncio.Event()
        self._recovery_lock = asyncio.Lock()
        self._next_recovery_at = 0.0

    async def run_async(self) -> None:
        consumers = [
            asyncio.create_task(self._consumer_loop_async())
            for _ in range(self._settings.concurrency)
        ]
        try:
            await self._shutdown.wait()
            await asyncio.gather(*consumers, return_exceptions=False)
        except asyncio.CancelledError:
            for consumer in consumers:
                consumer.cancel()
            await asyncio.gather(*consumers, return_exceptions=True)
            raise
        finally:
            await self._queue.close_async()

    async def stop_async(self) -> None:
        self._shutdown.set()

    async def _consumer_loop_async(self) -> None:
        while not self._shutdown.is_set():
            try:
                await self.run_once_async()
            except Exception:
                if not self._shutdown.is_set():
                    await asyncio.sleep(self._settings.poll_interval_seconds)

    async def run_once_async(self) -> bool:
        await self._recover_orphaned_if_due_async()
        try:
            message = await self._queue.receive_async(
                timeout_seconds=self._settings.receive_timeout_seconds
            )
        except AnalysisQueueInvalidMessageError as exc:
            if exc.analysis_id:
                await self._repository.mark_failed_if_active_async(
                    exc.analysis_id,
                    error_code="invalid_queue_job",
                    error_message="Analysis processing failed",
                )
                await self._repository.clear_raw_text_async(exc.analysis_id)
                with suppress(Exception):
                    await self._queue.delete_transient_payload_async(
                        exc.analysis_id
                    )
            return True

        if message is None:
            return False

        analysis = await self._repository.get_aggregate_by_id_async(
            message.job.analysis_id
        )
        if analysis is None:
            if message.job.analysis_type == "SOLDIER_CONCERN":
                with suppress(Exception):
                    await self._queue.delete_transient_payload_async(
                        message.job.analysis_id
                    )
            await self._queue.acknowledge_async(message)
            return True

        if analysis.status in {"completed", "failed"}:
            if analysis.analysis_type == "SOLDIER_CONCERN":
                with suppress(Exception):
                    await self._queue.delete_transient_payload_async(
                        message.job.analysis_id
                    )
            await self._queue.acknowledge_async(message)
            return True

        if analysis.analysis_type != message.job.analysis_type:
            await self._fail_permanently_async(message, "invalid_queue_job")
            return True

        claimed = await self._repository.try_claim_processing_async(
            message.job.analysis_id
        )
        if claimed is None:
            current = await self._repository.get_aggregate_by_id_async(
                message.job.analysis_id
            )
            if current is None or current.status in {"completed", "failed"}:
                await self._queue.acknowledge_async(message)
                return True

            if current.status == "processing":
                stale_before = datetime.now(UTC) - timedelta(
                    seconds=self._settings.processing_stale_seconds
                )
                recovered = await self._repository.recover_stale_processing_async(
                    message.job.analysis_id,
                    stale_before=stale_before,
                )
                if recovered:
                    claimed = await self._repository.try_claim_processing_async(
                        message.job.analysis_id
                    )

            if claimed is None:
                delay = self._busy_requeue_delay(current)
                await self._queue.requeue_async(
                    message,
                    delay_seconds=delay,
                    error_code="analysis_processing_busy",
                )
                return True

        if analysis.analysis_type == "SOLDIER_CONCERN":
            try:
                documents = await self._queue.get_transient_payload_async(
                    message.job.analysis_id
                )
            except Exception:
                await self._handle_retryable_failure_async(
                    message,
                    error_code="analysis_transient_transport_unavailable",
                )
                return True
            if documents is None:
                await self._fail_permanently_async(
                    message,
                    "analysis_processing_input_unavailable",
                )
                return True
        else:
            try:
                documents = await self._repository.get_documents_for_processing_async(
                    message.job.analysis_id
                )
            except ValueError:
                await self._fail_permanently_async(
                    message,
                    "analysis_processing_input_unavailable",
                )
                return True

        _logger.info(
            "analysis_worker_processing_started",
            extra={
                "event": "analysis_worker_processing_started",
                "analysis_id": message.job.analysis_id,
                "profile": message.job.analysis_type,
                "execution_mode": "async",
            },
        )
        heartbeat_stop = asyncio.Event()
        heartbeat = asyncio.create_task(
            self._heartbeat_async(message, heartbeat_stop)
        )
        try:
            await self._processor.process_claimed_async(
                analysis_id=message.job.analysis_id,
                analysis_type=message.job.analysis_type,
                documents=documents,
            )
        except AnalysisProcessingError:
            await self._handle_retryable_failure_async(
                message,
                error_code="analysis_processing_failed",
            )
        except Exception:
            await self._fail_permanently_async(
                message,
                "analysis_processing_failed",
            )
        else:
            if message.job.analysis_type == "SOLDIER_CONCERN":
                with suppress(Exception):
                    await self._queue.delete_transient_payload_async(
                        message.job.analysis_id
                    )
            await self._queue.acknowledge_async(message)
            _logger.info(
                "analysis_worker_processing_completed",
                extra={
                    "event": "analysis_worker_processing_completed",
                    "analysis_id": message.job.analysis_id,
                    "profile": message.job.analysis_type,
                    "execution_mode": "async",
                },
            )
        finally:
            heartbeat_stop.set()
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat

        return True

    async def _recover_orphaned_if_due_async(self) -> None:
        if monotonic() < self._next_recovery_at:
            return
        async with self._recovery_lock:
            if monotonic() < self._next_recovery_at:
                return
            await self._queue.recover_orphaned_async(
                limit=self._settings.recovery_batch_size
            )
            self._next_recovery_at = (
                monotonic() + self._settings.recovery_interval_seconds
            )

    async def _handle_retryable_failure_async(
        self,
        message: AnalysisQueueMessage,
        *,
        error_code: str,
    ) -> None:
        if message.attempt >= self._settings.maximum_attempts:
            await self._fail_permanently_async(
                message,
                "analysis_processing_failed",
            )
            return

        released = await self._repository.release_processing_for_retry_async(
            message.job.analysis_id
        )
        if not released:
            await self._queue.acknowledge_async(message)
            return

        if message.job.analysis_type == "SOLDIER_CONCERN":
            with suppress(Exception):
                await self._queue.touch_transient_payload_async(
                    message.job.analysis_id
                )

        await self._queue.requeue_async(
            message,
            delay_seconds=self._retry_delay(message.attempt),
            error_code=error_code,
        )

    async def _fail_permanently_async(
        self,
        message: AnalysisQueueMessage,
        error_code: str,
    ) -> None:
        await self._repository.mark_failed_if_active_async(
            message.job.analysis_id,
            error_code=error_code,
            error_message="Analysis processing failed",
        )
        await self._repository.clear_raw_text_async(message.job.analysis_id)
        if message.job.analysis_type == "SOLDIER_CONCERN":
            with suppress(Exception):
                await self._queue.delete_transient_payload_async(
                    message.job.analysis_id
                )
        await self._queue.fail_async(message, error_code=error_code)

    async def _heartbeat_async(
        self,
        message: AnalysisQueueMessage,
        stop: asyncio.Event,
    ) -> None:
        while not stop.is_set():
            try:
                await asyncio.wait_for(
                    stop.wait(),
                    timeout=self._settings.heartbeat_interval_seconds,
                )
            except TimeoutError:
                try:
                    if not await self._queue.extend_lease_async(message):
                        return
                except Exception:
                    return
                if message.job.analysis_type == "SOLDIER_CONCERN":
                    with suppress(Exception):
                        await self._queue.touch_transient_payload_async(
                            message.job.analysis_id
                        )

    def _retry_delay(self, attempt: int) -> float:
        delay = self._settings.retry_initial_delay_seconds * (2 ** max(0, attempt - 1))
        return min(delay, self._settings.retry_max_delay_seconds)

    def _busy_requeue_delay(self, analysis) -> float:
        if analysis.started_at is None:
            return self._settings.poll_interval_seconds
        stale_at = analysis.started_at + timedelta(
            seconds=self._settings.processing_stale_seconds
        )
        remaining = (stale_at - datetime.now(UTC)).total_seconds()
        return max(self._settings.poll_interval_seconds, remaining)
