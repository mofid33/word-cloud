from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from src.core.services.candidate.candidate_extraction_service import (
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


class StatisticalAnalysisServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = ConfigReader(env_type="development")
        cls.processor = PersianTextProcessor(PersianNlpResourceProvider(cls.config))
        cls.extractor = CandidateExtractionService(cls.config)
        cls.service = StatisticalAnalysisService(cls.config)

    def _occurrences(self, document_id: str, text: str, **metadata):
        return self.extractor.extract(
            document_id,
            self.processor.process(text),
            **metadata,
        )

    def test_frequency_document_frequency_and_coverage(self) -> None:
        occurrences = (
            self._occurrences("d1", "تحلیل تحلیل تحلیل")
            + self._occurrences("d2", "تحلیل داده")
            + self._occurrences("d3", "داده")
        )
        results = self.service.analyze(
            occurrences,
            document_ids=("d1", "d2", "d3"),
        )
        by_key = {item.canonical_text: item for item in results}
        analysis = by_key["تحلیل"]
        self.assertEqual(analysis.frequency, 4)
        self.assertEqual(analysis.document_frequency, 2)
        self.assertAlmostEqual(analysis.document_coverage, 2 / 3)
        self.assertEqual(
            len({item.document_id for item in analysis.occurrences}),
            2,
        )

    def test_repeated_occurrences_in_one_document_contribute_one_df(self) -> None:
        occurrences = self._occurrences("d1", "داده داده داده داده")
        result = self.service.analyze(
            occurrences,
            document_ids=("d1", "d2"),
        )
        data = next(item for item in result if item.canonical_text == "داده")
        self.assertEqual(data.frequency, 4)
        self.assertEqual(data.document_frequency, 1)
        self.assertEqual(data.document_coverage, 0.5)

    def test_relative_and_normalized_frequency_are_bounded(self) -> None:
        occurrences = (
            self._occurrences("d1", "تحلیل تحلیل داده")
            + self._occurrences("d2", "داده")
        )
        results = self.service.analyze(
            occurrences,
            document_ids=("d1", "d2"),
        )
        for item in results:
            self.assertGreaterEqual(item.relative_frequency, 0.0)
            self.assertLessEqual(item.relative_frequency, 1.0)
            self.assertGreaterEqual(item.normalized_frequency, 0.0)
            self.assertLessEqual(item.normalized_frequency, 1.0)

    def test_statistical_score_is_normalized_and_components_remain_available(self) -> None:
        occurrences = (
            self._occurrences("d1", "تحلیل داده تحلیل")
            + self._occurrences("d2", "تحلیل داده")
        )
        results = self.service.analyze(
            occurrences,
            document_ids=("d1", "d2"),
        )
        for item in results:
            self.assertGreaterEqual(item.statistical_score, 0.0)
            self.assertLessEqual(item.statistical_score, 1.0)
            self.assertGreaterEqual(item.phrase_quality, 0.0)
            self.assertLessEqual(item.phrase_quality, 1.0)
            self.assertGreaterEqual(item.document_coverage, 0.0)
            self.assertLessEqual(item.document_coverage, 1.0)

    def test_section_and_chunk_coverage_use_explicit_corpus_universe(self) -> None:
        occurrences = (
            self._occurrences(
                "d1",
                "تحلیل داده",
                section_id="s1",
                chunk_id="c1",
            )
            + self._occurrences(
                "d1",
                "تحلیل مدل",
                section_id="s2",
                chunk_id="c2",
            )
        )
        results = self.service.analyze(
            occurrences,
            document_ids=("d1",),
            section_keys=(("d1", "s1"), ("d1", "s2")),
            chunk_keys=(("d1", "c1"), ("d1", "c2")),
        )
        analysis = next(item for item in results if item.canonical_text == "تحلیل")
        self.assertEqual(analysis.section_coverage, 1.0)
        self.assertEqual(analysis.chunk_coverage, 1.0)
        data = next(item for item in results if item.canonical_text == "داده")
        self.assertEqual(data.section_coverage, 0.5)
        self.assertEqual(data.chunk_coverage, 0.5)

    def test_empty_filtered_section_and_chunk_remain_in_coverage_denominator(self) -> None:
        occurrences = self._occurrences(
            "d1",
            "تحلیل داده",
            section_id="s1",
            chunk_id="c1",
        )
        results = self.service.analyze(
            occurrences,
            document_ids=("d1",),
            section_keys=(("d1", "s1"), ("d1", "s2")),
            chunk_keys=(("d1", "c1"), ("d1", "c2")),
        )
        analysis = next(item for item in results if item.canonical_text == "تحلیل")
        self.assertEqual(analysis.section_coverage, 0.5)
        self.assertEqual(analysis.chunk_coverage, 0.5)

    def test_scope_metadata_is_required_when_occurrences_carry_boundaries(self) -> None:
        section_occurrences = self._occurrences(
            "d1",
            "تحلیل داده",
            section_id="s1",
        )
        with self.assertRaisesRegex(ValueError, "section_keys are required"):
            self.service.analyze(section_occurrences, document_ids=("d1",))

        chunk_occurrences = self._occurrences(
            "d1",
            "تحلیل داده",
            chunk_id="c1",
        )
        with self.assertRaisesRegex(ValueError, "chunk_keys are required"):
            self.service.analyze(chunk_occurrences, document_ids=("d1",))

    def test_scope_keys_must_reference_known_documents_and_occurrences(self) -> None:
        occurrences = self._occurrences(
            "d1",
            "تحلیل داده",
            section_id="s1",
        )
        with self.assertRaisesRegex(ValueError, "not present in document_ids"):
            self.service.analyze(
                occurrences,
                document_ids=("d1",),
                section_keys=(("d2", "s1"),),
            )
        with self.assertRaisesRegex(ValueError, "not present in section_keys"):
            self.service.analyze(
                occurrences,
                document_ids=("d1",),
                section_keys=(("d1", "s2"),),
            )

    def test_scope_keys_require_consistent_occurrence_metadata(self) -> None:
        unscoped = self._occurrences("d1", "تحلیل داده")
        with self.assertRaisesRegex(ValueError, "must contain section_id"):
            self.service.analyze(
                unscoped,
                document_ids=("d1",),
                section_keys=(("d1", "s1"),),
            )
        with self.assertRaisesRegex(ValueError, "must contain chunk_id"):
            self.service.analyze(
                unscoped,
                document_ids=("d1",),
                chunk_keys=(("d1", "c1"),),
            )

    def test_occurrence_tracking_preserves_source_boundaries(self) -> None:
        occurrences = self._occurrences(
            "d1",
            "تحلیل داده. تحلیل مدل",
            section_id="s1",
        )
        results = self.service.analyze(
            occurrences,
            document_ids=("d1",),
            section_keys=(("d1", "s1"),),
        )
        analysis = next(item for item in results if item.canonical_text == "تحلیل")
        self.assertEqual(analysis.frequency, 2)
        self.assertEqual(
            tuple(item.segment_index for item in analysis.occurrences),
            (0, 1),
        )

    def test_empty_input_is_supported(self) -> None:
        self.assertEqual(
            self.service.analyze((), document_ids=("d1",)),
            (),
        )
        self.assertEqual(
            self.service.analyze((), document_ids=()),
            (),
        )
        self.assertEqual(
            self.service.analyze(
                (),
                document_ids=("d1",),
                section_keys=(("d1", "s1"),),
                chunk_keys=(("d1", "c1"),),
            ),
            (),
        )

    def test_unknown_occurrence_document_fails_fast_without_content(self) -> None:
        occurrences = self._occurrences("d1", "متن خصوصی")
        with self.assertRaisesRegex(ValueError, "document_id"):
            self.service.analyze(occurrences, document_ids=("d2",))

    def test_duplicate_document_ids_are_invalid(self) -> None:
        with self.assertRaisesRegex(ValueError, "unique"):
            self.service.analyze((), document_ids=("d1", "d1"))

    def test_duplicate_scope_keys_are_invalid(self) -> None:
        with self.assertRaisesRegex(ValueError, "unique"):
            self.service.analyze(
                (),
                document_ids=("d1",),
                section_keys=(("d1", "s1"), ("d1", "s1")),
            )

    def test_ordering_and_repeated_execution_are_deterministic(self) -> None:
        occurrences = (
            self._occurrences("d2", "تحلیل داده")
            + self._occurrences("d1", "تحلیل مدل تحلیل")
        )
        first = self.service.analyze(
            occurrences,
            document_ids=("d1", "d2"),
        )
        second = self.service.analyze(
            occurrences,
            document_ids=("d1", "d2"),
        )
        self.assertEqual(first, second)
        self.assertEqual(
            list(first),
            sorted(
                first,
                key=lambda item: (
                    -item.statistical_score,
                    -item.frequency,
                    -item.ngram_size,
                    item.canonical_text,
                    item.text,
                ),
            ),
        )

    def test_invalid_statistical_weights_fail_fast(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = {
                "statistical_analysis": {
                    "weights": {
                        "frequency": 0.5,
                        "document_coverage": 0.5,
                        "phrase_quality": 0.5,
                    }
                }
            }
            for filename in ("appsettings.development.yaml", "appsettings.yaml"):
                (root / filename).write_text(
                    yaml.safe_dump(payload),
                    encoding="utf-8",
                )
            reader = ConfigReader(config_dir=root, env_type="development")
            with self.assertRaisesRegex(ValueError, "sum to 1.0"):
                StatisticalAnalysisService(reader)


if __name__ == "__main__":
    unittest.main()
