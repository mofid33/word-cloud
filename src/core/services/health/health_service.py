from __future__ import annotations

from sqlalchemy import text

from src.infrastructure.context.sql_db.psql_dbcontext import PsqlDbContext
from src.infrastructure.di.inject import inject
from src.infrastructure.observability.metrics_service import MetricsService
from src.infrastructure.providers.analysis_queue.redis_analysis_transient_payload_store import RedisAnalysisTransientPayloadStore


@inject
class HealthService:
    def __init__(self, db_context: PsqlDbContext, transient_store: RedisAnalysisTransientPayloadStore, metrics: MetricsService):
        self._db = db_context
        self._transient_store = transient_store
        self._metrics = metrics

    async def liveness_async(self) -> dict[str, object]:
        return {"status": "alive"}

    async def readiness_async(self) -> tuple[bool, dict[str, object]]:
        checks = {"postgres": False, "redis_transient": False}
        try:
            async with self._db.session() as session:
                await session.execute(text("SELECT 1"))
            checks["postgres"] = True
        except Exception:
            pass
        try:
            checks["redis_transient"] = await self._transient_store.ping_async()
        except Exception:
            pass
        ready = all(checks.values())
        self._metrics.set_readiness(ready)
        return ready, {"status": "ready" if ready else "not_ready", "checks": checks}
