from __future__ import annotations

import asyncio
import signal

from src.core.services.analysis.analysis_worker_service import AnalysisWorkerService
from src.infrastructure.di.bootstrap import bootstrap_di
from src.infrastructure.di.inject import resolve


async def _run_async() -> None:
    bootstrap_di()
    worker = resolve(AnalysisWorkerService)
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
    except asyncio.CancelledError:
        raise
    finally:
        await worker.stop_async()
        await run_task


def main() -> None:
    asyncio.run(_run_async())


if __name__ == "__main__":
    main()
