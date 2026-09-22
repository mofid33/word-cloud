import asyncio
import unittest

from src.core.services.analysis.analysis_execution_policy_service import (
    AnalysisExecutionPolicyError,
    AnalysisExecutionPolicyService,
)


class _Config:
    def __init__(self, overrides: dict[str, int] | None = None):
        self._values = {
            "analysis.limits.max_documents_per_analysis": 5,
            "analysis.limits.max_characters_per_document": 10,
            "analysis.limits.max_total_characters_per_analysis": 20,
            "analysis.sync_threshold.max_documents": 2,
            "analysis.sync_threshold.max_total_characters": 8,
        }
        self._values.update(overrides or {})

    def require(self, key: str) -> int:
        return self._values[key]


class AnalysisExecutionPolicyServiceTests(unittest.TestCase):
    def _service(
        self,
        overrides: dict[str, int] | None = None,
    ) -> AnalysisExecutionPolicyService:
        return AnalysisExecutionPolicyService(_Config(overrides))

    def test_auto_resolves_to_sync_when_both_thresholds_fit(self) -> None:
        result = asyncio.run(
            self._service().evaluate_async(
                execution_mode="auto",
                documents=[
                    {"document_id": "a", "text": "abc"},
                    {"document_id": "b", "text": "12"},
                ],
            )
        )

        self.assertEqual(result.requested_execution_mode, "auto")
        self.assertEqual(result.resolved_execution_mode, "sync")
        self.assertEqual(result.document_count, 2)
        self.assertEqual(result.total_characters, 5)

    def test_auto_resolves_to_async_when_sync_threshold_is_exceeded(self) -> None:
        result = asyncio.run(
            self._service().evaluate_async(
                execution_mode="auto",
                documents=[
                    {"document_id": "a", "text": "abc"},
                    {"document_id": "b", "text": "12"},
                    {"document_id": "c", "text": "x"},
                ],
            )
        )

        self.assertEqual(result.resolved_execution_mode, "async")

    def test_explicit_sync_over_threshold_is_rejected(self) -> None:
        with self.assertRaises(AnalysisExecutionPolicyError) as context:
            asyncio.run(
                self._service().evaluate_async(
                    execution_mode="sync",
                    documents=[
                        {"document_id": "a", "text": "12345"},
                        {"document_id": "b", "text": "6789"},
                    ],
                )
            )

        self.assertEqual(context.exception.code, "sync_threshold_exceeded")

    def test_hard_document_count_limit_is_enforced(self) -> None:
        with self.assertRaises(AnalysisExecutionPolicyError) as context:
            asyncio.run(
                self._service().evaluate_async(
                    execution_mode="async",
                    documents=[
                        {"document_id": str(index), "text": "x"}
                        for index in range(6)
                    ],
                )
            )

        self.assertEqual(context.exception.code, "max_documents_exceeded")

    def test_hard_per_document_character_limit_is_enforced_without_user_data(self) -> None:
        raw_text = "x" * 11
        user_controlled_id = "TOP-SECRET-DOCUMENT-ID"
        with self.assertRaises(AnalysisExecutionPolicyError) as context:
            asyncio.run(
                self._service().evaluate_async(
                    execution_mode="async",
                    documents=[
                        {
                            "document_id": user_controlled_id,
                            "text": raw_text,
                        },
                    ],
                )
            )

        self.assertEqual(
            context.exception.code,
            "max_document_characters_exceeded",
        )
        self.assertNotIn(raw_text, context.exception.message)
        self.assertNotIn(user_controlled_id, context.exception.message)

    def test_hard_total_character_limit_is_enforced(self) -> None:
        with self.assertRaises(AnalysisExecutionPolicyError) as context:
            asyncio.run(
                self._service(
                    {
                        "analysis.limits.max_characters_per_document": 20,
                    }
                ).evaluate_async(
                    execution_mode="async",
                    documents=[
                        {"document_id": "a", "text": "x" * 11},
                        {"document_id": "b", "text": "y" * 10},
                    ],
                )
            )

        self.assertEqual(
            context.exception.code,
            "max_total_characters_exceeded",
        )


if __name__ == "__main__":
    unittest.main()
