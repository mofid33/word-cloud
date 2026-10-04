from __future__ import annotations

import asyncio
import json
import os
import statistics
import subprocess
import time
import unittest

import httpx


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("values must not be empty")
    index = max(0, min(len(ordered) - 1, round(percentile * (len(ordered) - 1))))
    return ordered[index]


def _docker_stats(container_name: str) -> dict[str, str] | None:
    if not container_name:
        return None
    result = subprocess.run(
        [
            "docker",
            "stats",
            "--no-stream",
            "--format",
            "{{json .}}",
            container_name,
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return json.loads(result.stdout.strip().splitlines()[0])


@unittest.skipUnless(
    os.getenv("RUN_PHASE14_RUNTIME_BENCHMARK") == "1",
    "Set RUN_PHASE14_RUNTIME_BENCHMARK=1 to run the production HTTP runtime benchmark",
)
class Phase14RuntimePerformanceTests(unittest.TestCase):
    async def _measure(
        self,
        client: httpx.AsyncClient,
        *,
        method: str,
        path: str,
        requests: int,
        concurrency: int,
        json_body: dict | None = None,
    ) -> dict[str, float | int]:
        semaphore = asyncio.Semaphore(concurrency)
        latencies: list[float] = []

        async def one_request() -> None:
            async with semaphore:
                started = time.perf_counter()
                response = await client.request(method, path, json=json_body)
                elapsed = time.perf_counter() - started
                self.assertLess(response.status_code, 400, msg=response.text)
                latencies.append(elapsed)

        started = time.perf_counter()
        await asyncio.gather(*(one_request() for _ in range(requests)))
        total = time.perf_counter() - started

        return {
            "requests": requests,
            "concurrency": concurrency,
            "p50_ms": statistics.median(latencies) * 1000.0,
            "p95_ms": _percentile(latencies, 0.95) * 1000.0,
            "throughput_requests_per_second": requests / total,
            "wall_seconds": total,
        }

    async def _run_benchmark_async(self) -> None:
        base_url = os.getenv("PHASE14_BASE_URL", "http://127.0.0.1:5001")
        api_container = os.getenv(
            "PHASE14_API_CONTAINER",
            "word_cloud_phase14-api-1",
        )
        worker_container = os.getenv(
            "PHASE14_WORKER_CONTAINER",
            "word_cloud_phase14-worker-1",
        )
        validation_payload = {
            "analysis_type": "COURSE",
            "execution_mode": "auto",
            "documents": [
                {
                    "document_id": "phase14-benchmark-doc",
                    "text": "هوش مصنوعی پردازش زبان فارسی تحلیل داده",
                    "metadata": {},
                }
            ],
            "reference": "phase14-runtime-benchmark",
            "options": {},
        }

        timeout = httpx.Timeout(30.0)
        async with httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            trust_env=False,
        ) as client:
            live = await client.get("/api/v1/health/live")
            ready = await client.get("/api/v1/health/ready")
            self.assertEqual(live.status_code, 200)
            self.assertEqual(ready.status_code, 200)

            for _ in range(10):
                warmup = await client.get("/api/v1/health/live")
                self.assertEqual(warmup.status_code, 200)

            live_metrics = await self._measure(
                client,
                method="GET",
                path="/api/v1/health/live",
                requests=100,
                concurrency=20,
            )
            validation_metrics = await self._measure(
                client,
                method="POST",
                path="/api/v1/analysis/validate",
                requests=60,
                concurrency=10,
                json_body=validation_payload,
            )

        evidence = {
            "base_url": base_url,
            "device": "cpu",
            "vram_bytes": None,
            "live": live_metrics,
            "analysis_validate": validation_metrics,
            "api_container_stats": _docker_stats(api_container),
            "worker_container_stats": _docker_stats(worker_container),
            "status": "TARGET_MACHINE_BASELINE",
        }
        print(
            "PHASE14_RUNTIME_PERFORMANCE="
            + json.dumps(evidence, sort_keys=True, ensure_ascii=False)
        )

    def test_production_http_runtime_baseline(self) -> None:
        asyncio.run(self._run_benchmark_async())


if __name__ == "__main__":
    unittest.main()
