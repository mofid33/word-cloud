from __future__ import annotations

import os
import time
import unittest

from src.core.services.candidate.candidate_extraction_service import (
    CandidateDocument,
    CandidateExtractionService,
)
from src.core.services.persian_text.persian_text_processor import PersianTextProcessor
from src.core.services.statistical.statistical_analysis_service import (
    StatisticalAnalysisService,
)
from src.infrastructure.providers.persian_nlp.persian_nlp_resource_provider import (
    PersianNlpResourceProvider,
)
from src.infrastructure.utils.config_reader import ConfigReader


class CandidateStatisticalPerformanceBaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        config = ConfigReader(env_type="development")
        cls.processor = PersianTextProcessor(PersianNlpResourceProvider(config))
        cls.extractor = CandidateExtractionService(config)
        cls.statistical = StatisticalAnalysisService(config)

    def test_controlled_corpus_has_bounded_candidate_growth(self) -> None:
        document_count = 100
        repetitions_per_document = 20
        sentence = "تحلیل داده با هوش مصنوعی و یادگیری ماشین"
        documents = tuple(
            CandidateDocument(
                f"doc-{index:03d}",
                self.processor.process(
                    " ".join(sentence for _ in range(repetitions_per_document)),
                    domain="COURSE",
                ),
            )
            for index in range(document_count)
        )
        total_tokens = sum(
            len(document.processing_result.candidate_tokens)
            for document in documents
        )

        started = time.perf_counter()
        occurrences = self.extractor.extract_documents(documents)
        results = self.statistical.analyze(
            occurrences,
            document_ids=tuple(document.document_id for document in documents),
        )
        elapsed = time.perf_counter() - started

        self.assertLessEqual(len(occurrences), total_tokens * 3)
        self.assertTrue(results)

        configured_limit = os.getenv("PHASE7_PERF_MAX_SECONDS")
        if configured_limit:
            max_seconds = float(configured_limit)
            self.assertGreater(
                max_seconds,
                0.0,
                "PHASE7_PERF_MAX_SECONDS must be greater than zero",
            )
            self.assertLess(
                elapsed,
                max_seconds,
                "Phase 7 controlled performance baseline exceeded configured limit",
            )

        print(
            "Phase 7 performance baseline: "
            f"{elapsed:.3f}s, tokens={total_tokens}, occurrences={len(occurrences)}"
        )


if __name__ == "__main__":
    unittest.main()
