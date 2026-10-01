from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Response, status

from src.application.analysis.dtos.analysis_dto import ApiErrorEnvelopeDto
from src.core.services.visualization.visualization_service import (
    VisualizationFormatError,
    VisualizationNotFoundError,
    VisualizationService,
    VisualizationTopicNotFoundError,
    VisualizationUnavailableError,
)
from src.infrastructure.di.inject import inject


@inject
class VisualizationController:
    def __init__(self, visualization_service: VisualizationService):
        self._visualization_service = visualization_service

    def api(self) -> APIRouter:
        router = APIRouter(
            prefix="",
            tags=["Visualization"],
        )

        @router.get(
            "/{analysis_id}",
            response_class=Response,
            responses={
                status.HTTP_200_OK: {
                    "content": {
                        "image/png": {},
                        "image/svg+xml": {},
                    },
                    "description": "Derived visualization for a completed analysis",
                },
                status.HTTP_404_NOT_FOUND: {
                    "model": ApiErrorEnvelopeDto,
                    "description": "Analysis not found",
                },
                status.HTTP_409_CONFLICT: {
                    "model": ApiErrorEnvelopeDto,
                    "description": "Visualization is not available",
                },
                status.HTTP_422_UNPROCESSABLE_CONTENT: {
                    "model": ApiErrorEnvelopeDto,
                    "description": "Unsupported visualization format",
                },
            },
            summary="Render a completed analysis as PNG or SVG",
        )
        async def get_visualization(
            analysis_id: str,
            format: str = Query(default="png", min_length=1, max_length=10),
        ) -> Response:
            try:
                rendered = await self._visualization_service.render_async(
                    analysis_id,
                    format,
                )
            except VisualizationFormatError as exc:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail={"code": exc.code, "message": exc.message},
                ) from exc
            except VisualizationNotFoundError as exc:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"code": exc.code, "message": exc.message},
                ) from exc
            except VisualizationUnavailableError as exc:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"code": exc.code, "message": exc.message},
                ) from exc

            return Response(
                content=rendered.content,
                media_type=rendered.media_type,
                status_code=status.HTTP_200_OK,
            )

        @router.get(
            "/{analysis_id}/topics/{topic_id}",
            response_class=Response,
            responses={
                status.HTTP_200_OK: {
                    "content": {
                        "image/png": {},
                        "image/svg+xml": {},
                    },
                    "description": "Derived visualization for one persisted analysis topic",
                },
                status.HTTP_404_NOT_FOUND: {
                    "model": ApiErrorEnvelopeDto,
                    "description": "Analysis or topic not found",
                },
                status.HTTP_409_CONFLICT: {
                    "model": ApiErrorEnvelopeDto,
                    "description": "Topic visualization is not available",
                },
                status.HTTP_422_UNPROCESSABLE_CONTENT: {
                    "model": ApiErrorEnvelopeDto,
                    "description": "Unsupported visualization format",
                },
            },
            summary="Render one analysis topic as PNG or SVG",
        )
        async def get_topic_visualization(
            analysis_id: str,
            topic_id: str,
            format: str = Query(default="png", min_length=1, max_length=10),
        ) -> Response:
            try:
                rendered = await self._visualization_service.render_topic_async(
                    analysis_id,
                    topic_id,
                    format,
                )
            except VisualizationFormatError as exc:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail={"code": exc.code, "message": exc.message},
                ) from exc
            except (VisualizationNotFoundError, VisualizationTopicNotFoundError) as exc:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"code": exc.code, "message": exc.message},
                ) from exc
            except VisualizationUnavailableError as exc:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"code": exc.code, "message": exc.message},
                ) from exc

            return Response(
                content=rendered.content,
                media_type=rendered.media_type,
                status_code=status.HTTP_200_OK,
            )

        return router
