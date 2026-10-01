from __future__ import annotations

from fastapi import APIRouter, Response

from src.infrastructure.di.inject import inject
from src.infrastructure.observability.metrics_service import MetricsService
from src.infrastructure.providers.runtime.runtime_settings import RuntimeSettings


@inject
class MetricsController:
    def __init__(self, metrics: MetricsService, settings: RuntimeSettings):
        self._metrics = metrics
        self._settings = settings

    def api(self) -> APIRouter:
        router = APIRouter(prefix="", tags=["Metrics"])

        @router.get("/", include_in_schema=False)
        async def metrics() -> Response:
            if not self._settings.metrics_enabled:
                return Response(status_code=404)
            return Response(content=self._metrics.render(), media_type="text/plain; version=0.0.4; charset=utf-8")

        return router
