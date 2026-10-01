from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.core.services.health.health_service import HealthService
from src.infrastructure.di.inject import inject


@inject
class HealthController:
    def __init__(self, health_service: HealthService):
        self._health_service = health_service

    def api(self) -> APIRouter:
        router = APIRouter(prefix="", tags=["Health"])

        @router.get("/live", include_in_schema=False)
        async def live() -> dict[str, object]:
            return await self._health_service.liveness_async()

        @router.get("/ready", include_in_schema=False)
        async def ready() -> JSONResponse:
            is_ready, payload = await self._health_service.readiness_async()
            return JSONResponse(status_code=200 if is_ready else 503, content=payload)

        return router
