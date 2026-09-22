from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from src.infrastructure.context.sql_db.psql_dbcontext import PsqlDbContext
from src.infrastructure.di.inject import inject
from src.infrastructure.models.analysis_document import AnalysisDocument
from src.infrastructure.models.analysis_keyword import AnalysisKeyword
from src.infrastructure.models.analysis_topic import AnalysisTopic
from src.infrastructure.models.analysis_topic_keyword import AnalysisTopicKeyword
from src.infrastructure.models.word_cloud_analysis import WordCloudAnalysis
from src.infrastructure.repositories.base.base_repository import BaseRepository


@inject
class WordCloudAnalysisRepository(BaseRepository[WordCloudAnalysis]):
    def __init__(self, db_context: PsqlDbContext):
        super().__init__(db_context=db_context, model=WordCloudAnalysis)

    async def create_pending_async(
        self,
        *,
        analysis_type: str,
        execution_mode: str,
        documents: list[dict[str, Any]],
        reference: str | None = None,
        options: dict[str, Any] | None = None,
        persist_raw_text: bool = False,
    ) -> WordCloudAnalysis:
        if analysis_type == "SOLDIER_CONCERN" and persist_raw_text:
            raise ValueError(
                "Raw text persistence is forbidden for SOLDIER_CONCERN analyses"
            )

        is_soldier_concern = analysis_type == "SOLDIER_CONCERN"
        analysis = WordCloudAnalysis(
            analysis_type=analysis_type,
            status="pending",
            execution_mode=execution_mode,
            reference=None if is_soldier_concern else reference,
            options={} if is_soldier_concern else dict(options or {}),
        )
        for document in documents:
            request_metadata = dict(document.get("metadata") or {})
            persisted_metadata = (
                {} if is_soldier_concern else request_metadata
            )
            analysis.documents.append(
                AnalysisDocument(
                    document_id=self._persisted_document_id(
                        analysis_type,
                        str(document["document_id"]),
                    ),
                    role=(
                        None
                        if is_soldier_concern
                        else request_metadata.get("role")
                    ),
                    metadata_json=persisted_metadata,
                    raw_text=str(document["text"]) if persist_raw_text else None,
                )
            )

        async with self._db_context.session() as session:
            try:
                session.add(analysis)
                await session.commit()
                analysis_id = analysis.id
            except Exception:
                await session.rollback()
                raise

        saved = await self.get_aggregate_by_id_async(analysis_id)
        if saved is None:
            raise RuntimeError("Persisted analysis could not be reloaded")
        return saved

    async def get_aggregate_by_id_async(
        self,
        analysis_id: str,
    ) -> WordCloudAnalysis | None:
        async with self._db_context.session() as session:
            result = await session.execute(
                select(WordCloudAnalysis)
                .where(WordCloudAnalysis.id == analysis_id)
                .options(
                    selectinload(WordCloudAnalysis.documents),
                    selectinload(WordCloudAnalysis.keywords),
                    selectinload(WordCloudAnalysis.topics)
                    .selectinload(AnalysisTopic.keyword_links)
                    .selectinload(AnalysisTopicKeyword.keyword),
                )
            )
            return result.scalar_one_or_none()

    async def mark_processing_async(
        self,
        analysis_id: str,
        *,
        started_at: datetime | None = None,
    ) -> WordCloudAnalysis | None:
        return await self._update_lifecycle_async(
            analysis_id,
            status="processing",
            started_at=started_at or datetime.now(UTC),
        )

    async def mark_failed_async(
        self,
        analysis_id: str,
        *,
        error_code: str,
        error_message: str,
    ) -> WordCloudAnalysis | None:
        analysis = await self.get_by_id_async(analysis_id)
        if analysis is None:
            return None

        persisted_code = error_code
        persisted_message = error_message
        if analysis.analysis_type == "SOLDIER_CONCERN":
            persisted_code = "analysis_processing_failed"
            persisted_message = "Analysis processing failed"

        return await self._update_lifecycle_async(
            analysis_id,
            status="failed",
            completed_at=datetime.now(UTC),
            error_code=persisted_code,
            error_message=persisted_message,
        )

    async def save_result_atomically_async(
        self,
        *,
        analysis_id: str,
        keywords: list[dict[str, Any]],
        topics: list[dict[str, Any]],
        topic_keywords: list[dict[str, Any]],
        metrics: dict[str, Any],
        profile_result: dict[str, Any],
        model_version: str,
        scoring_version: str,
    ) -> WordCloudAnalysis:
        async with self._db_context.session() as session:
            try:
                analysis = await session.get(WordCloudAnalysis, analysis_id)
                if analysis is None:
                    raise LookupError(f"Analysis '{analysis_id}' does not exist")

                topic_ids_subquery = select(AnalysisTopic.id).where(
                    AnalysisTopic.analysis_id == analysis_id
                )
                await session.execute(
                    delete(AnalysisTopicKeyword).where(
                        AnalysisTopicKeyword.topic_id.in_(topic_ids_subquery)
                    )
                )
                await session.execute(
                    delete(AnalysisTopic).where(
                        AnalysisTopic.analysis_id == analysis_id
                    )
                )
                await session.execute(
                    delete(AnalysisKeyword).where(
                        AnalysisKeyword.analysis_id == analysis_id
                    )
                )

                keyword_ids: dict[str, str] = {}
                for item in keywords:
                    logical_id = str(item.get("keyword_id") or uuid4())
                    keyword_id = str(uuid4())
                    keyword_ids[logical_id] = keyword_id
                    session.add(
                        AnalysisKeyword(
                            id=keyword_id,
                            analysis_id=analysis_id,
                            text=str(item["text"]),
                            canonical_text=str(item["canonical_text"]),
                            rank=int(item["rank"]),
                            final_score=float(item["final_score"]),
                            statistical_score=float(item["statistical_score"]),
                            semantic_score=float(item["semantic_score"]),
                            coverage=float(item["coverage"]),
                            frequency=int(item["frequency"]),
                        )
                    )

                topic_ids: dict[str, str] = {}
                for item in topics:
                    logical_id = str(item.get("topic_id") or uuid4())
                    topic_id = str(uuid4())
                    topic_ids[logical_id] = topic_id
                    session.add(
                        AnalysisTopic(
                            id=topic_id,
                            analysis_id=analysis_id,
                            label=str(item["label"]),
                            rank=int(item["rank"]),
                            prevalence=float(item["prevalence"]),
                            coverage=float(item["coverage"]),
                            metadata_json=dict(item.get("metadata") or {}),
                        )
                    )

                for item in topic_keywords:
                    topic_key = str(item["topic_id"])
                    keyword_key = str(item["keyword_id"])
                    if topic_key not in topic_ids:
                        raise ValueError(
                            f"Unknown topic_id in topic_keywords: {topic_key}"
                        )
                    if keyword_key not in keyword_ids:
                        raise ValueError(
                            f"Unknown keyword_id in topic_keywords: {keyword_key}"
                        )
                    session.add(
                        AnalysisTopicKeyword(
                            topic_id=topic_ids[topic_key],
                            keyword_id=keyword_ids[keyword_key],
                            rank=int(item["rank"]),
                            relevance_score=float(item["relevance_score"]),
                        )
                    )

                analysis.status = "completed"
                analysis.model_version = model_version
                analysis.scoring_version = scoring_version
                analysis.metrics = dict(metrics)
                analysis.profile_result = dict(profile_result)
                analysis.completed_at = datetime.now(UTC)
                analysis.error_code = None
                analysis.error_message = None

                await session.commit()
            except Exception:
                await session.rollback()
                raise

        saved = await self.get_aggregate_by_id_async(analysis_id)
        if saved is None:
            raise RuntimeError("Completed analysis could not be reloaded")
        return saved

    @staticmethod
    def _persisted_document_id(
        analysis_type: str,
        document_id: str,
    ) -> str:
        if analysis_type != "SOLDIER_CONCERN":
            return document_id
        digest = sha256(document_id.encode("utf-8")).hexdigest()
        return f"sha256:{digest}"

    async def _update_lifecycle_async(
        self,
        analysis_id: str,
        **changes: Any,
    ) -> WordCloudAnalysis | None:
        async with self._db_context.session() as session:
            try:
                analysis = await session.get(WordCloudAnalysis, analysis_id)
                if analysis is None:
                    return None
                for field_name, value in changes.items():
                    setattr(analysis, field_name, value)
                await session.commit()
            except Exception:
                await session.rollback()
                raise

        return await self.get_aggregate_by_id_async(analysis_id)
