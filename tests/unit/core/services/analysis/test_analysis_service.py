import asyncio
import unittest

from src.core.services.analysis.analysis_execution_policy_service import (
    AnalysisExecutionPolicyError,
    AnalysisExecutionPolicyService,
)
from src.core.services.analysis.analysis_service import (
    AnalysisRequestValidationError,
    AnalysisService,
)


class _Config:
    def __init__(self):
        self._values = {
            "analysis.limits.max_documents_per_analysis": 5,
            "analysis.limits.max_characters_per_document": 10,
            "analysis.limits.max_total_characters_per_analysis": 20,
            "analysis.sync_threshold.max_documents": 2,
            "analysis.sync_threshold.max_total_characters": 8,
        }

    def require(self, key: str) -> int:
        return self._values[key]


class AnalysisServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        policy = AnalysisExecutionPolicyService(_Config())
        self.service = AnalysisService(policy)

    def test_rejects_duplicate_document_ids(self) -> None:
        async def run() -> None:
            with self.assertRaises(AnalysisRequestValidationError) as context:
                await self.service.validate_async(
                    analysis_type="COURSE",
                    execution_mode="auto",
                    documents=[
                        {"document_id": "same", "text": "الف", "metadata": {}},
                        {"document_id": "same", "text": "ب", "metadata": {}},
                    ],
                )
            self.assertEqual(context.exception.code, "duplicate_document_id")

        asyncio.run(run())

    def test_media_requires_supported_document_role(self) -> None:
        async def run() -> None:
            with self.assertRaises(AnalysisRequestValidationError) as context:
                await self.service.validate_async(
                    analysis_type="MEDIA",
                    execution_mode="auto",
                    documents=[
                        {
                            "document_id": "doc-1",
                            "text": "متن",
                            "metadata": {},
                        }
                    ],
                )
            self.assertEqual(
                context.exception.code,
                "media_document_role_required",
            )

        asyncio.run(run())

    def test_returns_request_metrics_without_retaining_raw_text(self) -> None:
        async def run() -> None:
            result = await self.service.validate_async(
                analysis_type="SOLDIER_CONCERN",
                execution_mode="sync",
                documents=[
                    {"document_id": "a", "text": "abc", "metadata": {}},
                    {"document_id": "b", "text": "12345", "metadata": {}},
                ],
            )
            self.assertEqual(result.document_count, 2)
            self.assertEqual(result.total_characters, 8)
            self.assertEqual(result.resolved_execution_mode, "sync")
            self.assertFalse(hasattr(result, "documents"))
            self.assertFalse(hasattr(result, "text"))

        asyncio.run(run())

    def test_auto_mode_is_resolved_by_execution_policy(self) -> None:
        result = asyncio.run(
            self.service.validate_async(
                analysis_type="COURSE",
                execution_mode="auto",
                documents=[
                    {"document_id": "a", "text": "abc", "metadata": {}},
                ],
            )
        )

        self.assertEqual(result.execution_mode, "auto")
        self.assertEqual(result.resolved_execution_mode, "sync")

    def test_rejects_raw_text_repeated_inside_metadata(self) -> None:
        with self.assertRaises(AnalysisRequestValidationError) as context:
            asyncio.run(
                self.service.validate_async(
                    analysis_type="SOLDIER_CONCERN",
                    execution_mode="sync",
                    documents=[
                        {
                            "document_id": "concern-1",
                            "text": "متن محرمانه",
                            "metadata": {
                                "nested": {"copy": "متن محرمانه"}
                            },
                        }
                    ],
                )
            )

        self.assertEqual(
            context.exception.code,
            "raw_text_repeated_in_metadata",
        )
        self.assertNotIn("متن محرمانه", context.exception.message)

    def test_execution_policy_error_is_not_swallowed(self) -> None:
        with self.assertRaises(AnalysisExecutionPolicyError) as context:
            asyncio.run(
                self.service.validate_async(
                    analysis_type="COURSE",
                    execution_mode="async",
                    documents=[
                        {
                            "document_id": "long",
                            "text": "x" * 11,
                            "metadata": {},
                        },
                    ],
                )
            )

        self.assertEqual(
            context.exception.code,
            "max_document_characters_exceeded",
        )


if __name__ == "__main__":
    unittest.main()
