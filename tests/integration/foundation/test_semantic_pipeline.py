from __future__ import annotations

import os
import unittest

from src.core.services.candidate.candidate_extraction_service import CandidateDocument, CandidateExtractionService
from src.core.services.persian_text.persian_text_processor import PersianTextProcessor
from src.core.services.semantic.semantic_analysis_service import SemanticAnalysisService
from src.core.services.statistical.statistical_analysis_service import StatisticalAnalysisService
from src.infrastructure.di.bootstrap import bootstrap_di
from src.infrastructure.di.inject import reset_di_state, resolve


@unittest.skipUnless(
    os.getenv("RUN_PHASE8_MODEL_INTEGRATION") == "1",
    "set RUN_PHASE8_MODEL_INTEGRATION=1 with configured models available",
)
class SemanticPipelineIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        reset_di_state()
        bootstrap_di()

    async def test_phase_6_to_phase_8_real_di_pipeline(self) -> None:
        processor = resolve(PersianTextProcessor)
        extractor = resolve(CandidateExtractionService)
        statistical = resolve(StatisticalAnalysisService)
        semantic = resolve(SemanticAnalysisService)

        text = "هوش مصنوعی و یادگیری ماشین در تحلیل داده و آموزش کاربرد دارند"
        document = CandidateDocument(
            "course-1",
            processor.process(text, domain="COURSE"),
            section_id="s1",
            chunk_id="c1",
        )
        occurrences = extractor.extract_documents((document,))
        stats = statistical.analyze(
            occurrences,
            document_ids=("course-1",),
            section_keys=(("course-1", "s1"),),
            chunk_keys=(("course-1", "c1"),),
        )
        result = await semantic.analyze_async(
            document.processing_result.embedding_text,
            stats,
        )

        self.assertEqual(len(result.candidates), len(stats))
        self.assertTrue(
            all(0.0 <= item.semantic_score <= 1.0 for item in result.candidates)
        )
        self.assertEqual(
            [item.rank for item in result.candidates],
            list(range(1, len(result.candidates) + 1)),
        )


if __name__ == "__main__":
    unittest.main()
