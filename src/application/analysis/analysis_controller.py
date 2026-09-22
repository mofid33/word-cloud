from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from src.application.analysis.dtos.analysis_dto import (
    AnalysisRequestDto,
    AnalysisValidationResponseDto,
    ApiErrorDto,
)
from src.core.services.analysis.analysis_service import (
    AnalysisRequestValidationError,
    AnalysisService,
)
from src.infrastructure.di.inject import inject


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
                status.HTTP_422_UNPROCESSABLE_ENTITY: {
                    "model": ApiErrorDto,
                    "description": "Request contract validation failed",
                }
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
            except AnalysisRequestValidationError as exc:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={
                        "code": exc.code,
                        "message": exc.message,
                    },
                ) from exc

            return AnalysisValidationResponseDto(
                analysis_type=result.analysis_type,
                execution_mode=result.execution_mode,
                document_count=result.document_count,
                total_characters=result.total_characters,
            )

        return router
