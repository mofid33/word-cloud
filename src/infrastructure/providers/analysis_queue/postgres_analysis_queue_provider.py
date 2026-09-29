from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from time import monotonic
from uuid import uuid4

from sqlalchemy import and_, delete, or_, select, update

from src.core.services.analysis.providers.analysis_queue_provider import (
    AnalysisQueueInvalidMessageError,
    AnalysisQueueJob,
    AnalysisQueueMessage,
    AnalysisQueueProvider,
)
from src.infrastructure.context.sql_db.psql_dbcontext import PsqlDbContext
from src.infrastructure.di.inject import inject
from src.infrastructure.models.analysis_queue_job import AnalysisQueueJobModel
from src.infrastructure.providers.analysis_queue.analysis_queue_settings import (
    AnalysisQueueSettings,
)


@inject
class PostgresAnalysisQueueProvider(AnalysisQueueProvider):
    __di_singleton__ = True

    def __init__(
        self,
        db_context: PsqlDbContext,
        settings: AnalysisQueueSettings,
    ):
        self._db_context = db_context
        self._settings = settings
        self._closed = False

    async def enqueue_async(
        self,
        analysis_id: str,
        payload: dict,
    ) -> None:
        if self._closed:
            raise RuntimeError("Analysis queue provider is closed")
        job = AnalysisQueueJob.from_payload(payload)
        if job.analysis_id != analysis_id:
            raise ValueError("Queue payload analysis_id does not match enqueue key")

        async with self._db_context.session() as session:
            try:
                session.add(
                    AnalysisQueueJobModel(
                        analysis_id=analysis_id,
                        payload=job.to_payload(),
                        state="queued",
                    )
                )
                await session.commit()
            except Exception:
                await session.rollback()
                raise

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
        now = datetime.now(UTC)
        receipt = str(uuid4())
        async with self._db_context.session() as session:
            try:
                result = await session.execute(
                    select(AnalysisQueueJobModel)
                    .where(
                        or_(
                            and_(
                                AnalysisQueueJobModel.state == "queued",
                                AnalysisQueueJobModel.available_at <= now,
                            ),
                            and_(
                                AnalysisQueueJobModel.state == "leased",
                                AnalysisQueueJobModel.lease_expires_at.is_not(None),
                                AnalysisQueueJobModel.lease_expires_at <= now,
                            ),
                        )
                    )
                    .order_by(
                        AnalysisQueueJobModel.available_at.asc(),
                        AnalysisQueueJobModel.created_at.asc(),
                    )
                    .with_for_update(skip_locked=True)
                    .limit(1)
                )
                item = result.scalar_one_or_none()
                if item is None:
                    await session.rollback()
                    return None

                try:
                    job = AnalysisQueueJob.from_payload(dict(item.payload or {}))
                except ValueError as exc:
                    analysis_id = item.analysis_id
                    await session.delete(item)
                    await session.commit()
                    raise AnalysisQueueInvalidMessageError(analysis_id) from exc

                item.state = "leased"
                item.attempt_count += 1
                item.lease_token = receipt
                item.lease_expires_at = now + timedelta(
                    seconds=self._settings.visibility_timeout_seconds
                )
                attempt = item.attempt_count
                await session.commit()
                return AnalysisQueueMessage(
                    job=job,
                    receipt=receipt,
                    attempt=attempt,
                )
            except AnalysisQueueInvalidMessageError:
                raise
            except Exception:
                await session.rollback()
                raise

    async def acknowledge_async(self, message: AnalysisQueueMessage) -> bool:
        return await self._delete_leased_async(message)

    async def fail_async(
        self,
        message: AnalysisQueueMessage,
        *,
        error_code: str,
    ) -> bool:
        self._validate_error_code(error_code)
        return await self._delete_leased_async(message)

    async def _delete_leased_async(self, message: AnalysisQueueMessage) -> bool:
        async with self._db_context.session() as session:
            result = await session.execute(
                delete(AnalysisQueueJobModel).where(
                    AnalysisQueueJobModel.analysis_id == message.job.analysis_id,
                    AnalysisQueueJobModel.state == "leased",
                    AnalysisQueueJobModel.lease_token == message.receipt,
                )
            )
            await session.commit()
            return bool(result.rowcount)

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
        async with self._db_context.session() as session:
            result = await session.execute(
                update(AnalysisQueueJobModel)
                .where(
                    AnalysisQueueJobModel.analysis_id == message.job.analysis_id,
                    AnalysisQueueJobModel.state == "leased",
                    AnalysisQueueJobModel.lease_token == message.receipt,
                )
                .values(
                    state="queued",
                    available_at=available_at,
                    lease_expires_at=None,
                    lease_token=None,
                    last_error_code=error_code,
                )
            )
            await session.commit()
            return bool(result.rowcount)

    async def extend_lease_async(self, message: AnalysisQueueMessage) -> bool:
        lease_expires_at = datetime.now(UTC) + timedelta(
            seconds=self._settings.visibility_timeout_seconds
        )
        async with self._db_context.session() as session:
            result = await session.execute(
                update(AnalysisQueueJobModel)
                .where(
                    AnalysisQueueJobModel.analysis_id == message.job.analysis_id,
                    AnalysisQueueJobModel.state == "leased",
                    AnalysisQueueJobModel.lease_token == message.receipt,
                )
                .values(lease_expires_at=lease_expires_at)
            )
            await session.commit()
            return bool(result.rowcount)

    async def close_async(self) -> None:
        self._closed = True

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
