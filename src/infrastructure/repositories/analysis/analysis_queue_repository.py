from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.dialects.postgresql import insert

from src.infrastructure.context.sql_db.psql_dbcontext import PsqlDbContext
from src.infrastructure.di.inject import inject
from src.infrastructure.models.analysis_queue_job import AnalysisQueueJobModel
from src.infrastructure.models.word_cloud_analysis import WordCloudAnalysis


@dataclass(frozen=True)
class LeasedAnalysisQueueJob:
    analysis_id: str
    payload: dict[str, Any]
    attempt: int
    receipt: str


@inject
class AnalysisQueueRepository:
    def __init__(self, db_context: PsqlDbContext):
        self._db_context = db_context

    async def enqueue_async(
        self,
        *,
        analysis_id: str,
        payload: dict[str, Any],
    ) -> None:
        async with self._db_context.session() as session:
            try:
                statement = (
                    insert(AnalysisQueueJobModel)
                    .values(
                        id=str(uuid4()),
                        analysis_id=analysis_id,
                        payload=dict(payload),
                        state="queued",
                    )
                    .on_conflict_do_nothing(
                        index_elements=[AnalysisQueueJobModel.analysis_id]
                    )
                )
                await session.execute(statement)
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def lease_next_async(
        self,
        *,
        receipt: str,
        visibility_timeout_seconds: float,
    ) -> LeasedAnalysisQueueJob | None:
        now = datetime.now(UTC)
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

                item.state = "leased"
                item.attempt_count += 1
                item.lease_token = receipt
                item.lease_expires_at = now + timedelta(
                    seconds=visibility_timeout_seconds
                )
                leased = LeasedAnalysisQueueJob(
                    analysis_id=item.analysis_id,
                    payload=dict(item.payload or {}),
                    attempt=item.attempt_count,
                    receipt=receipt,
                )
                await session.commit()
                return leased
            except Exception:
                await session.rollback()
                raise

    async def delete_leased_async(
        self,
        *,
        analysis_id: str,
        receipt: str,
    ) -> bool:
        async with self._db_context.session() as session:
            result = await session.execute(
                delete(AnalysisQueueJobModel).where(
                    AnalysisQueueJobModel.analysis_id == analysis_id,
                    AnalysisQueueJobModel.state == "leased",
                    AnalysisQueueJobModel.lease_token == receipt,
                )
            )
            await session.commit()
            return bool(result.rowcount)

    async def requeue_async(
        self,
        *,
        analysis_id: str,
        receipt: str,
        available_at: datetime,
        error_code: str,
    ) -> bool:
        async with self._db_context.session() as session:
            result = await session.execute(
                update(AnalysisQueueJobModel)
                .where(
                    AnalysisQueueJobModel.analysis_id == analysis_id,
                    AnalysisQueueJobModel.state == "leased",
                    AnalysisQueueJobModel.lease_token == receipt,
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

    async def extend_lease_async(
        self,
        *,
        analysis_id: str,
        receipt: str,
        visibility_timeout_seconds: float,
    ) -> bool:
        lease_expires_at = datetime.now(UTC) + timedelta(
            seconds=visibility_timeout_seconds
        )
        async with self._db_context.session() as session:
            result = await session.execute(
                update(AnalysisQueueJobModel)
                .where(
                    AnalysisQueueJobModel.analysis_id == analysis_id,
                    AnalysisQueueJobModel.state == "leased",
                    AnalysisQueueJobModel.lease_token == receipt,
                )
                .values(lease_expires_at=lease_expires_at)
            )
            await session.commit()
            return bool(result.rowcount)

    async def find_orphaned_pending_async(
        self,
        *,
        limit: int,
    ) -> list[tuple[str, str]]:
        async with self._db_context.session() as session:
            result = await session.execute(
                select(
                    WordCloudAnalysis.id,
                    WordCloudAnalysis.analysis_type,
                )
                .outerjoin(
                    AnalysisQueueJobModel,
                    AnalysisQueueJobModel.analysis_id == WordCloudAnalysis.id,
                )
                .where(
                    WordCloudAnalysis.status == "pending",
                    WordCloudAnalysis.execution_mode == "async",
                    AnalysisQueueJobModel.id.is_(None),
                )
                .order_by(WordCloudAnalysis.created_at.asc())
                .limit(limit)
            )
            return [(row[0], row[1]) for row in result.all()]
