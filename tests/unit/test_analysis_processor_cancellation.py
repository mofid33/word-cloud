import asyncio
import unittest

from src.core.services.analysis.analysis_processor_service import AnalysisProcessorService


class _CancellingProfile:
    async def analyze_async(self, _documents):
        raise asyncio.CancelledError()


class _Repository:
    def __init__(self):
        self.processing = []
        self.failed = []

    async def mark_processing_async(self, analysis_id):
        self.processing.append(analysis_id)

    async def mark_failed_async(self, analysis_id, *, error_code, error_message):
        self.failed.append((analysis_id, error_code, error_message))


class AnalysisProcessorCancellationTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancelled_sync_processing_closes_lifecycle(self):
        profile = _CancellingProfile()
        repository = _Repository()
        service = AnalysisProcessorService(
            course_analysis_service=profile,
            soldier_concern_analysis_service=profile,
            media_analysis_service=profile,
            analysis_repository=repository,
        )

        with self.assertRaises(asyncio.CancelledError):
            await service.process_async(
                analysis_id="analysis-1",
                analysis_type="COURSE",
                documents=[{"document_id": "doc-1", "text": "متن"}],
            )

        self.assertEqual(repository.processing, ["analysis-1"])
        self.assertEqual(
            repository.failed,
            [
                (
                    "analysis-1",
                    "analysis_processing_cancelled",
                    "Analysis processing was cancelled",
                )
            ],
        )


if __name__ == "__main__":
    unittest.main()
