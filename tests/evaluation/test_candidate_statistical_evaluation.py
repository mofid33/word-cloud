from __future__ import annotations

import json
import unittest
from pathlib import Path

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


class CandidateStatisticalEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        config = ConfigReader(env_type="development")
        cls.processor = PersianTextProcessor(PersianNlpResourceProvider(config))
        cls.extractor = CandidateExtractionService(config)
        cls.statistical = StatisticalAnalysisService(config)
        fixture_path = (
            Path(__file__).resolve().parent
            / "fixtures"
            / "candidate_statistical_cases.json"
        )
        cls.fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    def test_real_persian_candidate_and_noise_regression_fixture(self) -> None:
        documents = tuple(
            CandidateDocument(
                document["document_id"],
                self.processor.process(document["text"], domain="COURSE"),
                section_id=document["section_id"],
                chunk_id=document["chunk_id"],
            )
            for document in self.fixture["documents"]
        )
        occurrences = self.extractor.extract_documents(documents)
        results = self.statistical.analyze(
            occurrences,
            document_ids=tuple(document.document_id for document in documents),
        )
        texts = {item.text for item in results}

        for expected in self.fixture["expected_candidates"]:
            with self.subTest(expected=expected):
                self.assertIn(expected, texts)
        for forbidden in self.fixture["forbidden_candidates"]:
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, texts)

        by_key = {item.canonical_text: item for item in results}
        self.assertEqual(by_key["هوش مصنوعی"].document_frequency, 2)
        self.assertEqual(by_key["تحلیل داده"].document_frequency, 2)


if __name__ == "__main__":
    unittest.main()
