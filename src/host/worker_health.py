from __future__ import annotations

import asyncio

from src.core.services.health.health_service import HealthService
from src.infrastructure.context.sql_db.psql_dbcontext import PsqlDbContext
from src.infrastructure.di.inject import resolve
from src.infrastructure.providers.analysis_queue.redis_analysis_transient_payload_store import RedisAnalysisTransientPayloadStore


async def _main_async() -> int:
    service = resolve(HealthService)
    db = resolve(PsqlDbContext)
    redis_store = resolve(RedisAnalysisTransientPayloadStore)
    try:
        ready, _ = await service.readiness_async()
        return 0 if ready else 1
    finally:
        await redis_store.close_async()
        await db.dispose_async()


def main() -> None:
    raise SystemExit(asyncio.run(_main_async()))


if __name__ == "__main__":
    main()
