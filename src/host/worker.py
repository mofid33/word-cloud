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


async def _wait_for_shutdown_or_worker_exit_async(
    run_task: asyncio.Task,
    stop_requested: asyncio.Event,
) -> bool:
    stop_wait_task = asyncio.create_task(stop_requested.wait())
    try:
        done, _ = await asyncio.wait(
            {run_task, stop_wait_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if run_task in done:
            await run_task
            if not stop_requested.is_set():
                raise RuntimeError("Analysis worker stopped unexpectedly")
            return False
        return True
    finally:
        stop_wait_task.cancel()
        await asyncio.gather(stop_wait_task, return_exceptions=True)


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
        shutdown_requested = await _wait_for_shutdown_or_worker_exit_async(
            run_task,
            stop_requested,
        )
        if shutdown_requested:
            logger.info(
                "worker_shutdown_requested",
                extra={"event": "worker_shutdown_requested"},
            )
    except asyncio.CancelledError:
        raise
    finally:
        await worker.stop_async()
        if not run_task.done():
            try:
                await asyncio.wait_for(
                    run_task,
                    timeout=runtime_settings.graceful_shutdown_seconds,
                )
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
