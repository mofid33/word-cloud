from __future__ import annotations

import unittest

from src.core.services.candidate.candidate_extraction_service import (
    CandidateDocument,
    CandidateExtractionService,
)
from src.core.services.persian_text.persian_text_processor import PersianTextProcessor
from src.core.services.statistical.statistical_analysis_service import (
    StatisticalAnalysisService,
)
from src.infrastructure.di.bootstrap import bootstrap_di
from src.infrastructure.di.inject import reset_di_state, resolve


class CandidateStatisticalPipelineIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_di_state()
        bootstrap_di()

    def test_phase_6_to_phase_7_pipeline_uses_real_discovery_and_di(self) -> None:
        processor = resolve(PersianTextProcessor)
        extractor = resolve(CandidateExtractionService)
        statistical = resolve(StatisticalAnalysisService)

        documents = (
            CandidateDocument(
                "course-1",
                processor.process(
                    "هوش مصنوعی در تحلیل داده. مدل GPT-4 کاربرد دارد",
                    domain="COURSE",
                ),
                section_id="intro",
                chunk_id="c1",
            ),
            CandidateDocument(
                "course-2",
                processor.process(
                    "تحلیل داده و هوش مصنوعی برای یادگیری ماشین مفید است",
                    domain="COURSE",
                ),
                section_id="methods",
                chunk_id="c2",
            ),
        )
        occurrences = extractor.extract_documents(documents)
        results = statistical.analyze(
            occurrences,
            document_ids=("course-1", "course-2"),
            section_keys=tuple(
                (document.document_id, document.section_id)
                for document in documents
                if document.section_id is not None
            ),
            chunk_keys=tuple(
                (document.document_id, document.chunk_id)
                for document in documents
                if document.chunk_id is not None
            ),
        )
        by_key = {item.canonical_text: item for item in results}

        self.assertIn("هوش مصنوعی", by_key)
        self.assertIn("تحلیل داده", by_key)
        self.assertIn("GPT-4", by_key)
        self.assertEqual(by_key["هوش مصنوعی"].document_frequency, 2)
        self.assertEqual(by_key["هوش مصنوعی"].document_coverage, 1.0)
        self.assertTrue(by_key["هوش مصنوعی"].is_protected)
        self.assertTrue(all(0.0 <= item.statistical_score <= 1.0 for item in results))


if __name__ == "__main__":
    unittest.main()
