import asyncio
import unittest

from src.core.services.analysis.analysis_service import (
    AnalysisRequestValidationError,
    AnalysisService,
)


class AnalysisServiceTests(unittest.TestCase):
    def test_rejects_duplicate_document_ids(self) -> None:
        service = AnalysisService()

        async def run() -> None:
            with self.assertRaises(AnalysisRequestValidationError) as context:
                await service.validate_async(
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
        service = AnalysisService()

        async def run() -> None:
            with self.assertRaises(AnalysisRequestValidationError) as context:
                await service.validate_async(
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
        service = AnalysisService()

        async def run() -> None:
            result = await service.validate_async(
                analysis_type="SOLDIER_CONCERN",
                execution_mode="sync",
                documents=[
                    {"document_id": "a", "text": "abc", "metadata": {}},
                    {"document_id": "b", "text": "12345", "metadata": {}},
                ],
            )
            self.assertEqual(result.document_count, 2)
            self.assertEqual(result.total_characters, 8)
            self.assertFalse(hasattr(result, "documents"))
            self.assertFalse(hasattr(result, "text"))

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
