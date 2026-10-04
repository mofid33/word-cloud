from __future__ import annotations

import asyncio
import logging
import signal

from src.core.services.analysis.analysis_worker_service import AnalysisWorkerService
from src.infrastructure.context.sql_db.psql_dbcontext import PsqlDbContext
from src.infrastructure.di.bootstrap import bootstrap_di
from src.infrastructure.di.inject import resolve
from src.infrastructure.observability.logging_config import configure_logging
from src.infrastructure.providers.runtime.runtime_settings import RuntimeSettings


async def _run_async() -> None:
    bootstrap_di()
    runtime_settings = resolve(RuntimeSettings)
    configure_logging(runtime_settings.log_level)
    worker = resolve(AnalysisWorkerService)
    db_context = resolve(PsqlDbContext)
    logger = logging.getLogger("word_cloud.worker.host")
    loop = asyncio.get_running_loop()
    stop_requested = asyncio.Event()

    def request_stop() -> None:
        stop_requested.set()

    for signal_name in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signal_name, request_stop)
        except (NotImplementedError, RuntimeError):
            pass

    run_task = asyncio.create_task(worker.run_async())
    try:
        await stop_requested.wait()
        logger.info(
            "worker_shutdown_requested",
            extra={"event": "worker_shutdown_requested"},
        )
    except asyncio.CancelledError:
        raise
    finally:
        await worker.stop_async()
        try:
            await asyncio.wait_for(run_task, timeout=runtime_settings.graceful_shutdown_seconds)
        except TimeoutError:
            run_task.cancel()
            await asyncio.gather(run_task, return_exceptions=True)
        await db_context.dispose_async()
        logger.info(
            "worker_shutdown_complete",
            extra={"event": "worker_shutdown_complete"},
        )


def main() -> None:
    asyncio.run(_run_async())


if __name__ == "__main__":
    main()
