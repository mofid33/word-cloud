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
from src.infrastructure.providers.persian_nlp.persian_nlp_resource_provider import (
    PersianNlpResourceProvider,
)
from src.infrastructure.utils.config_reader import ConfigReader


class CandidateStatisticalProfileRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        config = ConfigReader(env_type="development")
        cls.processor = PersianTextProcessor(PersianNlpResourceProvider(config))
        cls.extractor = CandidateExtractionService(config)
        cls.statistical = StatisticalAnalysisService(config)

    def test_course_section_coverage_counts_filtered_empty_sections(self) -> None:
        documents = (
            CandidateDocument(
                "course-1",
                self.processor.process("تحلیل داده", domain="COURSE"),
                section_id="s1",
                chunk_id="c1",
            ),
            CandidateDocument(
                "course-1",
                self.processor.process("در و برای", domain="COURSE"),
                section_id="s2",
                chunk_id="c2",
            ),
        )
        occurrences = self.extractor.extract_documents(documents)
        results = self.statistical.analyze(
            occurrences,
            document_ids=("course-1",),
            section_keys=(("course-1", "s1"), ("course-1", "s2")),
            chunk_keys=(("course-1", "c1"), ("course-1", "c2")),
        )
        analysis = next(item for item in results if item.canonical_text == "تحلیل")
        self.assertEqual(analysis.document_coverage, 1.0)
        self.assertEqual(analysis.section_coverage, 0.5)
        self.assertEqual(analysis.chunk_coverage, 0.5)

    def test_soldier_concern_repetition_in_one_concern_does_not_inflate_df(self) -> None:
        documents = (
            CandidateDocument(
                "concern-1",
                self.processor.process(
                    "کمبود مرخصی کمبود مرخصی",
                    domain="SOLDIER_CONCERN",
                ),
            ),
            CandidateDocument(
                "concern-2",
                self.processor.process(
                    "کمبود مرخصی شدید است",
                    domain="SOLDIER_CONCERN",
                ),
            ),
            CandidateDocument(
                "concern-3",
                self.processor.process(
                    "کیفیت غذا پایین است",
                    domain="SOLDIER_CONCERN",
                ),
            ),
        )
        occurrences = self.extractor.extract_documents(documents)
        results = self.statistical.analyze(
            occurrences,
            document_ids=("concern-1", "concern-2", "concern-3"),
        )
        shortage = next(
            item for item in results if item.canonical_text == "کمبود مرخصی"
        )
        self.assertEqual(shortage.frequency, 3)
        self.assertEqual(shortage.document_frequency, 2)
        self.assertAlmostEqual(shortage.document_coverage, 2 / 3)

    def test_media_content_and_feedback_corpora_can_be_analyzed_separately(self) -> None:
        content_documents = (
            CandidateDocument(
                "content-1",
                self.processor.process(
                    "هوش مصنوعی در آموزش کاربرد دارد",
                    domain="MEDIA",
                ),
            ),
            CandidateDocument(
                "content-2",
                self.processor.process(
                    "پردازش زبان طبیعی برای آموزش مفید است",
                    domain="MEDIA",
                ),
            ),
        )
        feedback_documents = (
            CandidateDocument(
                "feedback-1",
                self.processor.process(
                    "کیفیت صدا ضعیف است",
                    domain="MEDIA",
                ),
            ),
            CandidateDocument(
                "feedback-2",
                self.processor.process(
                    "کیفیت صدا بهتر شد",
                    domain="MEDIA",
                ),
            ),
        )

        content_results = self.statistical.analyze(
            self.extractor.extract_documents(content_documents),
            document_ids=("content-1", "content-2"),
        )
        feedback_results = self.statistical.analyze(
            self.extractor.extract_documents(feedback_documents),
            document_ids=("feedback-1", "feedback-2"),
        )

        content_keys = {item.canonical_text for item in content_results}
        feedback_keys = {item.canonical_text for item in feedback_results}
        self.assertIn("هوش مصنوعی", content_keys)
        self.assertNotIn("کیفیت صدا", content_keys)
        self.assertIn("کیفیت صدا", feedback_keys)
        self.assertNotIn("هوش مصنوعی", feedback_keys)


if __name__ == "__main__":
    unittest.main()
