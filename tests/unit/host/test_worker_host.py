from __future__ import annotations

import asyncio
import unittest

from src.host.worker import _wait_for_shutdown_or_worker_exit_async


class WorkerHostTests(unittest.TestCase):
    def test_shutdown_signal_wins_without_worker_failure(self) -> None:
        async def run():
            stop_requested = asyncio.Event()

            async def worker_loop():
                await asyncio.Event().wait()

            run_task = asyncio.create_task(worker_loop())
            stop_requested.set()
            shutdown_requested = await _wait_for_shutdown_or_worker_exit_async(
                run_task,
                stop_requested,
            )
            self.assertTrue(shutdown_requested)
            run_task.cancel()
            await asyncio.gather(run_task, return_exceptions=True)

        asyncio.run(run())

    def test_unexpected_worker_exit_is_fatal(self) -> None:
        async def run():
            stop_requested = asyncio.Event()

            async def worker_loop():
                return None

            run_task = asyncio.create_task(worker_loop())
            await asyncio.sleep(0)
            with self.assertRaisesRegex(
                RuntimeError,
                "Analysis worker stopped unexpectedly",
            ):
                await _wait_for_shutdown_or_worker_exit_async(
                    run_task,
                    stop_requested,
                )

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
