from __future__ import annotations

import json
import statistics
import time
import tracemalloc
import unittest

from tests.evaluation.phase10_test_support import build_profile_services


class Phase10ProfilePerformanceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.services = build_profile_services()

    async def _measure(self, profile, documents, iterations=3):
        durations = []
        tracemalloc.start()
        try:
            for _ in range(iterations):
                started = time.perf_counter()
                result = await self.services[profile].analyze_async(documents)
                durations.append(time.perf_counter() - started)
                self.assertTrue(result.keywords)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()

        ordered = sorted(durations)
        p50 = statistics.median(ordered)
        p95_index = max(0, min(len(ordered) - 1, round(0.95 * (len(ordered) - 1))))
        p95 = ordered[p95_index]
        total_documents = len(documents) * iterations
        throughput = total_documents / sum(durations)
        return {
            "iterations": iterations,
            "documents_per_iteration": len(documents),
            "p50_seconds": p50,
            "p95_seconds": p95,
            "documents_per_second": throughput,
            "peak_python_bytes": peak,
            "semantic_provider": "deterministic_fixture_not_production_model",
        }

    async def test_course_long_document_orchestration_baseline(self):
        documents = [
            {
                "document_id": f"course-{index:02d}",
                "text": (
                    "هوش مصنوعی یادگیری ماشین تحلیل داده "
                    "پردازش زبان فارسی آموزش مدل"
                ),
                "metadata": {
                    "section_id": f"section-{index:02d}",
                    "chunk_id": f"chunk-{index:02d}",
                },
            }
            for index in range(12)
        ]
        evidence = await self._measure("COURSE", documents)
        print(
            "PHASE10_COURSE_ORCHESTRATION_PERFORMANCE="
            + json.dumps(evidence, sort_keys=True)
        )

    async def test_soldier_multi_document_orchestration_baseline(self):
        documents = [
            {
                "document_id": f"concern-{index:03d}",
                "text": "کیفیت اینترنت آموزش ارتباط خانواده خدمات",
                "metadata": {},
            }
            for index in range(50)
        ]
        evidence = await self._measure("SOLDIER_CONCERN", documents)
        print(
            "PHASE10_SOLDIER_ORCHESTRATION_PERFORMANCE="
            + json.dumps(evidence, sort_keys=True)
        )

    async def test_media_two_role_orchestration_baseline(self):
        documents = [
            {
                "document_id": f"published-{index:02d}",
                "text": "اقتصاد دیجیتال هوش مصنوعی رسانه فناوری",
                "metadata": {"role": "published_content"},
            }
            for index in range(20)
        ] + [
            {
                "document_id": f"audience-{index:02d}",
                "text": "کیفیت اینترنت مخاطب رسانه ارتباط دیجیتال",
                "metadata": {"role": "audience_feedback"},
            }
            for index in range(20)
        ]
        evidence = await self._measure("MEDIA", documents)
        print(
            "PHASE10_MEDIA_ORCHESTRATION_PERFORMANCE="
            + json.dumps(evidence, sort_keys=True)
        )


if __name__ == "__main__":
    unittest.main()
