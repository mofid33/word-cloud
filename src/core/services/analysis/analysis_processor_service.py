from __future__ import annotations

from typing import Any

from src.core.services.analysis.profile_result import StructuredProfileResult
from src.core.services.course.course_analysis_service import CourseAnalysisService
from src.core.services.media.media_analysis_service import MediaAnalysisService
from src.core.services.soldier_concern.soldier_concern_analysis_service import (
    SoldierConcernAnalysisService,
)
from src.infrastructure.di.inject import inject
from src.infrastructure.repositories.analysis.word_cloud_analysis_repository import (
    WordCloudAnalysisRepository,
)


class AnalysisProcessingError(RuntimeError):
    def __init__(self):
        super().__init__("Analysis processing failed")
        self.code = "analysis_processing_failed"
        self.message = "Analysis processing failed"


@inject
class AnalysisProcessorService:
    def __init__(
        self,
        course_analysis_service: CourseAnalysisService,
        soldier_concern_analysis_service: SoldierConcernAnalysisService,
        media_analysis_service: MediaAnalysisService,
        analysis_repository: WordCloudAnalysisRepository,
    ):
        self._course = course_analysis_service
        self._soldier = soldier_concern_analysis_service
        self._media = media_analysis_service
        self._repository = analysis_repository

    async def process_async(
        self,
        *,
        analysis_id: str,
        analysis_type: str,
        documents: list[dict[str, Any]],
    ) -> StructuredProfileResult:
        self._service_for(analysis_type)
        await self._repository.mark_processing_async(analysis_id)
        try:
            return await self.process_claimed_async(
                analysis_id=analysis_id,
                analysis_type=analysis_type,
                documents=documents,
            )
        except AnalysisProcessingError:
            await self._repository.mark_failed_async(
                analysis_id,
                error_code="analysis_processing_failed",
                error_message="Analysis processing failed",
            )
            raise

    async def process_claimed_async(
        self,
        *,
        analysis_id: str,
        analysis_type: str,
        documents: list[dict[str, Any]],
    ) -> StructuredProfileResult:
        service = self._service_for(analysis_type)
        try:
            result = await service.analyze_async(documents)
            persisted_keyword_ids = {
                item.canonical_text for item in result.keywords
            }
            await self._repository.save_result_atomically_async(
                analysis_id=analysis_id,
                keywords=[
                    {
                        "keyword_id": item.canonical_text,
                        "text": item.text,
                        "canonical_text": item.canonical_text,
                        "rank": item.rank,
                        "final_score": item.final_score,
                        "statistical_score": item.statistical_score,
                        "semantic_score": item.semantic_score,
                        "coverage": item.coverage,
                        "frequency": item.frequency,
                    }
                    for item in result.keywords
                ],
                topics=[
                    {
                        "topic_id": item.topic_id,
                        "label": item.label,
                        "rank": item.rank,
                        "prevalence": item.prevalence,
                        "coverage": item.coverage,
                        "metadata": {
                            **dict(item.metadata),
                            "document_ids": list(item.document_ids),
                        },
                    }
                    for item in result.topics
                ],
                topic_keywords=[
                    {
                        "topic_id": topic.topic_id,
                        "keyword_id": keyword.canonical_text,
                        "rank": keyword.rank,
                        "relevance_score": keyword.relevance_score,
                    }
                    for topic in result.topics
                    for keyword in topic.representative_keyphrases
                    if keyword.canonical_text in persisted_keyword_ids
                ],
                metrics=dict(result.metrics),
                profile_result=dict(result.profile_result),
                model_version=result.model_version,
                scoring_version=result.scoring_version,
            )
            return result
        except AnalysisProcessingError:
            raise
        except Exception as exc:
            raise AnalysisProcessingError() from exc

    def _service_for(self, analysis_type: str):
        if analysis_type == "COURSE":
            return self._course
        if analysis_type == "SOLDIER_CONCERN":
            return self._soldier
        if analysis_type == "MEDIA":
            return self._media
        raise ValueError("Unsupported analysis_type")
