from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.core.services.analysis.analysis_execution_policy_service import (
    AnalysisExecutionPolicyService,
)
from src.core.services.analysis.analysis_processor_service import AnalysisProcessorService
from src.infrastructure.di.inject import inject
from src.infrastructure.repositories.analysis.word_cloud_analysis_repository import (
    WordCloudAnalysisRepository,
)


class AnalysisRequestValidationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class AnalysisNotFoundError(LookupError):
    def __init__(self):
        super().__init__("Analysis was not found")
        self.code = "analysis_not_found"
        self.message = "Analysis was not found"


class AnalysisResultUnavailableError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class AnalysisValidationResult:
    analysis_type: str
    execution_mode: str
    resolved_execution_mode: str
    document_count: int
    total_characters: int


@dataclass(frozen=True)
class AnalysisErrorResult:
    code: str
    message: str


@dataclass(frozen=True)
class AnalysisStatusResult:
    analysis_id: str
    analysis_type: str
    status: str
    execution_mode: str
    reference: str | None
    model_version: str | None
    scoring_version: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    error: AnalysisErrorResult | None


@dataclass(frozen=True)
class AnalysisKeywordResult:
    text: str
    canonical_text: str
    rank: int
    final_score: float
    statistical_score: float
    semantic_score: float
    coverage: float
    frequency: int


@dataclass(frozen=True)
class AnalysisTopicKeywordResult:
    text: str
    canonical_text: str
    rank: int
    relevance_score: float


@dataclass(frozen=True)
class AnalysisTopicResult:
    topic_id: str
    label: str
    rank: int
    prevalence: float
    coverage: float
    keywords: tuple[AnalysisTopicKeywordResult, ...]


@dataclass(frozen=True)
class AnalysisStructuredResult:
    analysis: AnalysisStatusResult
    keywords: tuple[AnalysisKeywordResult, ...]
    topics: tuple[AnalysisTopicResult, ...]
    metrics: dict[str, Any]
    profile_result: dict[str, Any]


@inject
class AnalysisService:
    def __init__(
        self,
        execution_policy_service: AnalysisExecutionPolicyService,
        analysis_processor_service: AnalysisProcessorService,
        analysis_repository: WordCloudAnalysisRepository,
    ):
        self._execution_policy_service = execution_policy_service
        self._analysis_processor_service = analysis_processor_service
        self._analysis_repository = analysis_repository

    async def validate_async(
        self,
        *,
        analysis_type: str,
        execution_mode: str,
        documents: list[dict[str, Any]],
    ) -> AnalysisValidationResult:
        if analysis_type not in {"COURSE", "SOLDIER_CONCERN", "MEDIA"}:
            raise AnalysisRequestValidationError(
                "unsupported_analysis_type",
                "analysis_type must be COURSE, SOLDIER_CONCERN, or MEDIA",
            )

        document_ids = [str(document["document_id"]) for document in documents]
        if len(set(document_ids)) != len(document_ids):
            raise AnalysisRequestValidationError(
                "duplicate_document_id",
                "document_id values must be unique within an analysis request",
            )

        for document in documents:
            raw_text = str(document["text"])
            metadata = document.get("metadata") or {}
            if self._contains_raw_text(metadata, raw_text):
                raise AnalysisRequestValidationError(
                    "raw_text_repeated_in_metadata",
                    "Document metadata must not repeat the document raw text",
                )

        if analysis_type == "MEDIA":
            allowed_roles = {"published_content", "audience_feedback"}
            for document in documents:
                metadata = document.get("metadata") or {}
                role = metadata.get("role")
                if role not in allowed_roles:
                    raise AnalysisRequestValidationError(
                        "media_document_role_required",
                        "MEDIA documents require metadata.role equal to "
                        "'published_content' or 'audience_feedback'",
                    )

        decision = await self._execution_policy_service.evaluate_async(
            execution_mode=execution_mode,
            documents=documents,
        )

        return AnalysisValidationResult(
            analysis_type=analysis_type,
            execution_mode=decision.requested_execution_mode,
            resolved_execution_mode=decision.resolved_execution_mode,
            document_count=decision.document_count,
            total_characters=decision.total_characters,
        )

    async def create_async(
        self,
        *,
        analysis_type: str,
        execution_mode: str,
        documents: list[dict[str, Any]],
        reference: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> AnalysisStatusResult:
        validation = await self.validate_async(
            analysis_type=analysis_type,
            execution_mode=execution_mode,
            documents=documents,
        )
        analysis = await self._analysis_repository.create_pending_async(
            analysis_type=analysis_type,
            execution_mode=validation.resolved_execution_mode,
            documents=documents,
            reference=reference,
            options=options,
            persist_raw_text=False,
        )
        if validation.resolved_execution_mode == "sync":
            await self._analysis_processor_service.process_async(
                analysis_id=analysis.id,
                analysis_type=analysis_type,
                documents=documents,
            )
            completed = await self._analysis_repository.get_aggregate_by_id_async(
                analysis.id
            )
            if completed is None:
                raise RuntimeError("Completed analysis could not be reloaded")
            return self._status_result(completed)
        return self._status_result(analysis)

    async def get_status_async(
        self,
        analysis_id: str,
    ) -> AnalysisStatusResult:
        analysis = await self._analysis_repository.get_aggregate_by_id_async(
            analysis_id
        )
        if analysis is None:
            raise AnalysisNotFoundError()
        return self._status_result(analysis)

    async def get_result_async(
        self,
        analysis_id: str,
    ) -> AnalysisStructuredResult:
        analysis = await self._analysis_repository.get_aggregate_by_id_async(
            analysis_id
        )
        if analysis is None:
            raise AnalysisNotFoundError()

        if analysis.status == "failed":
            raise AnalysisResultUnavailableError(
                "analysis_failed",
                "Analysis failed and has no result",
            )
        if analysis.status != "completed":
            raise AnalysisResultUnavailableError(
                "analysis_result_not_ready",
                "Analysis result is not ready",
            )

        keywords = tuple(
            AnalysisKeywordResult(
                text=item.text,
                canonical_text=item.canonical_text,
                rank=item.rank,
                final_score=item.final_score,
                statistical_score=item.statistical_score,
                semantic_score=item.semantic_score,
                coverage=item.coverage,
                frequency=item.frequency,
            )
            for item in sorted(
                analysis.keywords,
                key=lambda value: value.rank,
            )
        )

        topics: list[AnalysisTopicResult] = []
        for topic in sorted(
            analysis.topics,
            key=lambda value: value.rank,
        ):
            topic_keywords = tuple(
                AnalysisTopicKeywordResult(
                    text=link.keyword.text,
                    canonical_text=link.keyword.canonical_text,
                    rank=link.rank,
                    relevance_score=link.relevance_score,
                )
                for link in sorted(
                    topic.keyword_links,
                    key=lambda value: value.rank,
                )
            )
            topics.append(
                AnalysisTopicResult(
                    topic_id=topic.id,
                    label=topic.label,
                    rank=topic.rank,
                    prevalence=topic.prevalence,
                    coverage=topic.coverage,
                    keywords=topic_keywords,
                )
            )

        return AnalysisStructuredResult(
            analysis=self._status_result(analysis),
            keywords=keywords,
            topics=tuple(topics),
            metrics=dict(analysis.metrics or {}),
            profile_result=dict(analysis.profile_result or {}),
        )

    @staticmethod
    def _status_result(analysis: Any) -> AnalysisStatusResult:
        error: AnalysisErrorResult | None = None
        if analysis.error_code is not None or analysis.error_message is not None:
            error = AnalysisErrorResult(
                code=analysis.error_code or "analysis_error",
                message=analysis.error_message or "Analysis failed",
            )

        return AnalysisStatusResult(
            analysis_id=analysis.id,
            analysis_type=analysis.analysis_type,
            status=analysis.status,
            execution_mode=analysis.execution_mode,
            reference=analysis.reference,
            model_version=analysis.model_version,
            scoring_version=analysis.scoring_version,
            created_at=analysis.created_at,
            started_at=analysis.started_at,
            completed_at=analysis.completed_at,
            error=error,
        )

    @classmethod
    def _contains_raw_text(cls, value: Any, raw_text: str) -> bool:
        if not raw_text:
            return False
        if isinstance(value, str):
            return raw_text in value
        if isinstance(value, dict):
            return any(
                cls._contains_raw_text(key, raw_text)
                or cls._contains_raw_text(child, raw_text)
                for key, child in value.items()
            )
        if isinstance(value, (list, tuple)):
            return any(
                cls._contains_raw_text(child, raw_text)
                for child in value
            )
        return False
