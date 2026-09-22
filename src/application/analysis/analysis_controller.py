from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from src.application.analysis.dtos.analysis_dto import (
    AnalysisRequestDto,
    AnalysisValidationResponseDto,
    ApiErrorEnvelopeDto,
)
from src.core.services.analysis.analysis_execution_policy_service import (
    AnalysisExecutionPolicyError,
)
from src.core.services.analysis.analysis_service import (
    AnalysisRequestValidationError,
    AnalysisService,
)
from src.infrastructure.di.inject import inject


_PAYLOAD_TOO_LARGE_CODES = {
    "max_documents_exceeded",
    "max_document_characters_exceeded",
    "max_total_characters_exceeded",
}


@inject
class AnalysisController:
    def __init__(self, analysis_service: AnalysisService):
        self._analysis_service = analysis_service

    def api(self) -> APIRouter:
        router = APIRouter(
            prefix="",
            tags=["Analysis"],
        )

        @router.post(
            "/validate",
            response_model=AnalysisValidationResponseDto,
            status_code=status.HTTP_200_OK,
            responses={
                status.HTTP_413_CONTENT_TOO_LARGE: {
                    "model": ApiErrorEnvelopeDto,
                    "description": "Configured analysis input limit exceeded",
                },
                status.HTTP_422_UNPROCESSABLE_CONTENT: {
                    "model": ApiErrorEnvelopeDto,
                    "description": "Request contract or execution policy validation failed",
                },
            },
            summary="Validate an analysis request",
        )
        async def validate_analysis(
            payload: AnalysisRequestDto,
        ) -> AnalysisValidationResponseDto:
            try:
                result = await self._analysis_service.validate_async(
                    analysis_type=payload.analysis_type.value,
                    execution_mode=payload.execution_mode.value,
                    documents=[
                        document.model_dump()
                        for document in payload.documents
                    ],
                )
            except AnalysisExecutionPolicyError as exc:
                http_status = (
                    status.HTTP_413_CONTENT_TOO_LARGE
                    if exc.code in _PAYLOAD_TOO_LARGE_CODES
                    else status.HTTP_422_UNPROCESSABLE_CONTENT
                )
                raise HTTPException(
                    status_code=http_status,
                    detail={
                        "code": exc.code,
                        "message": exc.message,
                    },
                ) from exc
            except AnalysisRequestValidationError as exc:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail={
                        "code": exc.code,
                        "message": exc.message,
                    },
                ) from exc

            return AnalysisValidationResponseDto(
                analysis_type=result.analysis_type,
                execution_mode=result.execution_mode,
                resolved_execution_mode=result.resolved_execution_mode,
                document_count=result.document_count,
                total_characters=result.total_characters,
            )

        return router
