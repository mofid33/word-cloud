from __future__ import annotations

import unittest

from src.core.services.analysis.analysis_processor_service import (
    AnalysisProcessingError,
    AnalysisProcessorService,
)
from src.core.services.analysis.profile_result import StructuredProfileResult


class _Profile:
    def __init__(self, profile, *, fail=False):
        self.profile = profile
        self.fail = fail
        self.calls = 0

    async def analyze_async(self, documents):
        self.calls += 1
        if self.fail:
            raise RuntimeError("RAW-SECRET-SHOULD-NOT-LEAK")
        return StructuredProfileResult(
            profile=self.profile,
            keywords=(),
            metrics={"document_count": len(documents)},
            profile_result={"profile": self.profile},
            model_version="model-v1",
            scoring_version="score-v1",
        )


class _Repository:
    def __init__(self):
        self.processing = []
        self.saved = []
        self.failed = []

    async def mark_processing_async(self, analysis_id):
        self.processing.append(analysis_id)

    async def save_result_atomically_async(self, **kwargs):
        self.saved.append(kwargs)

    async def mark_failed_async(self, analysis_id, **kwargs):
        self.failed.append((analysis_id, kwargs))


class AnalysisProcessorServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_dispatches_each_profile_without_embedding_profile_logic(self):
        course = _Profile("COURSE")
        soldier = _Profile("SOLDIER_CONCERN")
        media = _Profile("MEDIA")
        repository = _Repository()
        processor = AnalysisProcessorService(course, soldier, media, repository)

        for analysis_type, expected in (
            ("COURSE", course),
            ("SOLDIER_CONCERN", soldier),
            ("MEDIA", media),
        ):
            result = await processor.process_async(
                analysis_id=f"id-{analysis_type}",
                analysis_type=analysis_type,
                documents=[{"document_id": "d", "text": "safe", "metadata": {}}],
            )
            self.assertEqual(result.profile, analysis_type)
            self.assertEqual(expected.calls, 1)

        self.assertEqual(len(repository.saved), 3)
        self.assertTrue(all(item["topics"] == [] for item in repository.saved))
        self.assertTrue(all(item["topic_keywords"] == [] for item in repository.saved))

    async def test_failure_is_sanitized_before_persistence_and_raise(self):
        raw = "RAW-SECRET-SHOULD-NOT-LEAK"
        repository = _Repository()
        processor = AnalysisProcessorService(
            _Profile("COURSE", fail=True),
            _Profile("SOLDIER_CONCERN"),
            _Profile("MEDIA"),
            repository,
        )

        with self.assertRaises(AnalysisProcessingError) as context:
            await processor.process_async(
                analysis_id="analysis-1",
                analysis_type="COURSE",
                documents=[{"document_id": "d", "text": raw, "metadata": {}}],
            )

        self.assertNotIn(raw, str(context.exception))
        self.assertEqual(repository.failed[0][1]["error_message"], "Analysis processing failed")
        self.assertNotIn(raw, repr(repository.failed))

    async def test_unknown_profile_does_not_start_processing(self):
        repository = _Repository()
        processor = AnalysisProcessorService(
            _Profile("COURSE"),
            _Profile("SOLDIER_CONCERN"),
            _Profile("MEDIA"),
            repository,
        )
        with self.assertRaisesRegex(ValueError, "Unsupported analysis_type"):
            await processor.process_async(
                analysis_id="analysis-1",
                analysis_type="UNKNOWN",
                documents=[],
            )
        self.assertEqual(repository.processing, [])


if __name__ == "__main__":
    unittest.main()
