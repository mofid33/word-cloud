from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from time import monotonic
from typing import Any
from uuid import uuid4

from src.core.services.analysis.providers.analysis_queue_provider import (
    AnalysisQueueInvalidMessageError,
    AnalysisQueueJob,
    AnalysisQueueMessage,
    AnalysisQueueProvider,
)
from src.infrastructure.di.inject import inject
from src.infrastructure.providers.analysis_queue.analysis_queue_settings import (
    AnalysisQueueSettings,
)
from src.infrastructure.providers.analysis_queue.redis_analysis_transient_payload_store import (
    RedisAnalysisTransientPayloadStore,
)
from src.infrastructure.repositories.analysis.analysis_queue_repository import (
    AnalysisQueueRepository,
)


@inject
class PostgresAnalysisQueueProvider(AnalysisQueueProvider):
    __di_singleton__ = True

    def __init__(
        self,
        queue_repository: AnalysisQueueRepository,
        settings: AnalysisQueueSettings,
        transient_payload_store: RedisAnalysisTransientPayloadStore,
    ):
        self._queue_repository = queue_repository
        self._settings = settings
        self._transient_payload_store = transient_payload_store
        self._closed = False

    async def enqueue_async(
        self,
        analysis_id: str,
        payload: dict[str, Any],
    ) -> None:
        if self._closed:
            raise RuntimeError("Analysis queue provider is closed")
        job = AnalysisQueueJob.from_payload(payload)
        if job.analysis_id != analysis_id:
            raise ValueError("Queue payload analysis_id does not match enqueue key")
        await self._queue_repository.enqueue_async(
            analysis_id=analysis_id,
            payload=job.to_payload(),
        )

    async def receive_async(
        self,
        *,
        timeout_seconds: float,
    ) -> AnalysisQueueMessage | None:
        if self._closed:
            return None
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or timeout_seconds <= 0
        ):
            raise ValueError("timeout_seconds must be positive")

        deadline = monotonic() + float(timeout_seconds)
        while not self._closed:
            message = await self._try_receive_once_async()
            if message is not None:
                return message
            remaining = deadline - monotonic()
            if remaining <= 0:
                return None
            await asyncio.sleep(min(self._settings.poll_interval_seconds, remaining))
        return None

    async def _try_receive_once_async(self) -> AnalysisQueueMessage | None:
        receipt = str(uuid4())
        leased = await self._queue_repository.lease_next_async(
            receipt=receipt,
            visibility_timeout_seconds=self._settings.visibility_timeout_seconds,
        )
        if leased is None:
            return None

        try:
            job = AnalysisQueueJob.from_payload(leased.payload)
        except ValueError as exc:
            await self._queue_repository.delete_leased_async(
                analysis_id=leased.analysis_id,
                receipt=leased.receipt,
            )
            raise AnalysisQueueInvalidMessageError(leased.analysis_id) from exc

        return AnalysisQueueMessage(
            job=job,
            receipt=leased.receipt,
            attempt=leased.attempt,
        )

    async def acknowledge_async(self, message: AnalysisQueueMessage) -> bool:
        return await self._queue_repository.delete_leased_async(
            analysis_id=message.job.analysis_id,
            receipt=message.receipt,
        )

    async def fail_async(
        self,
        message: AnalysisQueueMessage,
        *,
        error_code: str,
    ) -> bool:
        self._validate_error_code(error_code)
        return await self._queue_repository.delete_leased_async(
            analysis_id=message.job.analysis_id,
            receipt=message.receipt,
        )

    async def requeue_async(
        self,
        message: AnalysisQueueMessage,
        *,
        delay_seconds: float,
        error_code: str,
    ) -> bool:
        self._validate_error_code(error_code)
        if (
            isinstance(delay_seconds, bool)
            or not isinstance(delay_seconds, (int, float))
            or delay_seconds < 0
        ):
            raise ValueError("delay_seconds must be non-negative")
        available_at = datetime.now(UTC) + timedelta(seconds=float(delay_seconds))
        return await self._queue_repository.requeue_async(
            analysis_id=message.job.analysis_id,
            receipt=message.receipt,
            available_at=available_at,
            error_code=error_code,
        )

    async def extend_lease_async(self, message: AnalysisQueueMessage) -> bool:
        return await self._queue_repository.extend_lease_async(
            analysis_id=message.job.analysis_id,
            receipt=message.receipt,
            visibility_timeout_seconds=self._settings.visibility_timeout_seconds,
        )

    async def recover_orphaned_async(self, *, limit: int) -> int:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be a positive integer")
        orphaned = await self._queue_repository.find_orphaned_pending_async(
            limit=limit
        )
        recovered = 0
        for analysis_id, analysis_type in orphaned:
            job = AnalysisQueueJob.create(
                analysis_id=analysis_id,
                analysis_type=analysis_type,
            )
            await self.enqueue_async(analysis_id, job.to_payload())
            recovered += 1
        return recovered

    async def put_transient_payload_async(
        self,
        analysis_id: str,
        documents: list[dict[str, Any]],
    ) -> None:
        await self._transient_payload_store.put_async(analysis_id, documents)

    async def get_transient_payload_async(
        self,
        analysis_id: str,
    ) -> list[dict[str, Any]] | None:
        return await self._transient_payload_store.get_async(analysis_id)

    async def touch_transient_payload_async(self, analysis_id: str) -> bool:
        return await self._transient_payload_store.touch_async(analysis_id)

    async def delete_transient_payload_async(self, analysis_id: str) -> None:
        await self._transient_payload_store.delete_async(analysis_id)

    async def close_async(self) -> None:
        self._closed = True
        await self._transient_payload_store.close_async()

    @staticmethod
    def _validate_error_code(error_code: str) -> None:
        if (
            not isinstance(error_code, str)
            or not error_code
            or len(error_code) > 100
            or any(
                not (character.islower() or character.isdigit() or character in "_-.")
                for character in error_code
            )
        ):
            raise ValueError("Queue error_code is invalid")
