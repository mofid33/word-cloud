import unittest

from src.core.services.analysis.analysis_execution_policy_service import (
    AnalysisExecutionPolicyError,
    AnalysisExecutionPolicyService,
)


class _Config:
    def __init__(self):
        self.values = {
            "analysis.limits.max_documents_per_analysis": 5000,
            "analysis.limits.max_characters_per_document": 500000,
            "analysis.limits.max_total_characters_per_analysis": 10000000,
            "analysis.sync_threshold.max_documents": 20,
            "analysis.sync_threshold.max_total_characters": 100000,
            "analysis.sync_threshold.max_estimated_candidates": 1500,
            "analysis.sync_threshold.course_max_total_characters": 8000,
            "analysis.sync_threshold.course_max_estimated_candidates": 1200,
            "analysis.sync_threshold.processing_timeout_seconds": 240,
        }

    def require(self, key):
        return self.values[key]


class CourseAdaptiveExecutionPolicyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.service = AnalysisExecutionPolicyService(_Config())

    async def test_course_auto_switches_long_document_to_async(self):
        decision = await self.service.evaluate_async(
            analysis_type="COURSE",
            execution_mode="auto",
            documents=[{"text": "الف" * 9000}],
        )
        self.assertEqual(decision.resolved_execution_mode, "async")

    async def test_non_course_keeps_global_sync_threshold(self):
        decision = await self.service.evaluate_async(
            analysis_type="MEDIA",
            execution_mode="auto",
            documents=[{"text": "الف" * 9000}],
        )
        self.assertEqual(decision.resolved_execution_mode, "sync")

    async def test_explicit_sync_rejects_expensive_course_input(self):
        with self.assertRaises(AnalysisExecutionPolicyError) as context:
            await self.service.evaluate_async(
                analysis_type="COURSE",
                execution_mode="sync",
                documents=[{"text": "الف" * 9000}],
            )
        self.assertEqual(context.exception.code, "sync_threshold_exceeded")


if __name__ == "__main__":
    unittest.main()
