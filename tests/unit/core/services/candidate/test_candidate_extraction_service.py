from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from src.core.services.candidate.candidate_extraction_service import (
    CandidateDocument,
    CandidateExtractionService,
)
from src.core.services.persian_text.persian_text_processor import PersianTextProcessor
from src.infrastructure.providers.persian_nlp.persian_nlp_resource_provider import (
    PersianNlpResourceProvider,
)
from src.infrastructure.utils.config_reader import ConfigReader


class CandidateExtractionServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = ConfigReader(env_type="development")
        cls.processor = PersianTextProcessor(PersianNlpResourceProvider(cls.config))
        cls.service = CandidateExtractionService(cls.config)

    def _extract(self, text: str, document_id: str = "doc-1"):
        return self.service.extract(document_id, self.processor.process(text))

    def test_extracts_unigram_bigram_and_trigram_but_never_fourgram(self) -> None:
        results = self._extract("تحلیل داده پیشرفته کاربردی")
        sizes = {item.ngram_size for item in results}
        self.assertEqual(sizes, {1, 2, 3})
        self.assertFalse(any(item.ngram_size == 4 for item in results))
        self.assertIn("تحلیل داده", {item.text for item in results})
        self.assertIn("تحلیل داده پیشرفته", {item.text for item in results})

    def test_does_not_cross_punctuation_segment_boundary(self) -> None:
        results = self._extract("تحلیل داده. یادگیری ماشین")
        texts = {item.text for item in results}
        self.assertNotIn("داده یادگیری", texts)
        self.assertNotIn("تحلیل داده یادگیری", texts)
        self.assertIn("تحلیل داده", texts)
        self.assertIn("یادگیری ماشین", texts)

    def test_documents_are_never_joined_for_ngram_generation(self) -> None:
        documents = (
            CandidateDocument("doc-a", self.processor.process("تحلیل داده")),
            CandidateDocument("doc-b", self.processor.process("یادگیری ماشین")),
        )
        results = self.service.extract_documents(documents)
        texts = {item.text for item in results}
        self.assertNotIn("داده یادگیری", texts)
        self.assertEqual({item.document_id for item in results}, {"doc-a", "doc-b"})

    def test_persian_latin_and_mixed_candidates_are_preserved(self) -> None:
        texts = {
            item.text
            for item in self._extract("مدل فارسی BERT برای NLP فارسی")
        }
        self.assertIn("مدل", texts)
        self.assertIn("BERT", texts)
        self.assertIn("BERT برای پردازش", texts)
        self.assertIn("پردازش زبان طبیعی", texts)

    def test_technical_compound_tokens_are_not_resplit(self) -> None:
        texts = {
            item.text
            for item in self._extract("GPT-4 BERT-base v1.2 2026/09")
        }
        self.assertIn("GPT-4", texts)
        self.assertIn("BERT-base", texts)
        self.assertIn("v1.2", texts)
        self.assertIn("2026/09", texts)

    def test_numeric_noise_is_filtered_but_year_and_date_are_preserved(self) -> None:
        texts = {item.text for item in self._extract("۱۲ ۲۰۲۶ 2026/09 مدل")}
        self.assertNotIn("۱۲", texts)
        self.assertIn("۲۰۲۶", texts)
        self.assertIn("2026/09", texts)

    def test_protected_unigram_and_multi_token_phrase_survive_filtering(self) -> None:
        results = self._extract("هوش مصنوعی و نرم‌افزار")
        by_text = {item.text: item for item in results}
        self.assertTrue(by_text["هوش"].is_protected)
        self.assertTrue(by_text["هوش مصنوعی"].is_protected)
        self.assertTrue(by_text["نرم‌افزار"].is_protected)

    def test_stopword_unigram_and_edge_stopword_are_filtered(self) -> None:
        texts = {item.text for item in self._extract("در تحلیل داده")}
        self.assertNotIn("در", texts)
        self.assertNotIn("در تحلیل", texts)
        self.assertIn("تحلیل", texts)
        self.assertIn("تحلیل داده", texts)

    def test_internal_stopword_does_not_invalidate_phrase(self) -> None:
        texts = {item.text for item in self._extract("تحلیل و داده")}
        self.assertIn("تحلیل و داده", texts)
        self.assertNotIn("و", texts)

    def test_pos_x_is_not_rejected(self) -> None:
        processed = self.processor.process("زیبا پروژه")
        self.assertEqual(processed.candidate_tokens[0].pos, "X")
        texts = {item.text for item in self.service.extract("doc-x", processed)}
        self.assertIn("زیبا", texts)
        self.assertIn("زیبا پروژه", texts)

    def test_function_pos_unigram_is_rejected_conservatively(self) -> None:
        texts = {item.text for item in self._extract("من تحلیل داده")}
        self.assertNotIn("من", texts)
        self.assertIn("تحلیل", texts)

    def test_section_and_chunk_metadata_are_preserved(self) -> None:
        result = self.service.extract(
            "doc-1",
            self.processor.process("تحلیل داده"),
            section_id="section-1",
            chunk_id="chunk-1",
        )
        self.assertTrue(result)
        self.assertTrue(all(item.section_id == "section-1" for item in result))
        self.assertTrue(all(item.chunk_id == "chunk-1" for item in result))

    def test_ordering_and_repeated_execution_are_deterministic(self) -> None:
        first = self._extract("تحلیل داده و یادگیری ماشین")
        second = self._extract("تحلیل داده و یادگیری ماشین")
        self.assertEqual(first, second)
        self.assertEqual(
            list(first),
            sorted(
                first,
                key=lambda item: (
                    item.segment_index,
                    item.token_start,
                    item.ngram_size,
                    item.canonical_text,
                    item.text,
                ),
            ),
        )

    def test_empty_and_single_token_inputs(self) -> None:
        self.assertEqual(self._extract(""), ())
        single = self._extract("تحلیل")
        self.assertEqual(len(single), 1)
        self.assertEqual(single[0].text, "تحلیل")

    def test_noisy_input_does_not_create_punctuation_candidates(self) -> None:
        texts = {item.text for item in self._extract("### تحلیل 🙂 ... داده !!!")}
        self.assertEqual(texts, {"تحلیل", "داده"})

    def test_invalid_identifier_fails_without_raw_text_in_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "document_id"):
            self.service.extract(" ", self.processor.process("متن خصوصی"))

    def test_invalid_ngram_configuration_fails_fast(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = {
                "candidate_extraction": {
                    "minimum_ngram": 1,
                    "maximum_ngram": 4,
                    "maximum_phrase_characters": 120,
                    "filter_pure_numeric": True,
                    "preserve_four_digit_year": True,
                    "filter_stopword_unigrams": True,
                    "filter_edge_stopwords": True,
                    "reject_function_pos_unigrams": True,
                }
            }
            for filename in ("appsettings.development.yaml", "appsettings.yaml"):
                (root / filename).write_text(
                    yaml.safe_dump(payload),
                    encoding="utf-8",
                )
            reader = ConfigReader(config_dir=root, env_type="development")
            with self.assertRaisesRegex(ValueError, "exactly 1..3"):
                CandidateExtractionService(reader)

    def test_filtering_is_configurable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = {
                "candidate_extraction": {
                    "minimum_ngram": 1,
                    "maximum_ngram": 3,
                    "maximum_phrase_characters": 120,
                    "filter_pure_numeric": False,
                    "preserve_four_digit_year": True,
                    "filter_stopword_unigrams": False,
                    "filter_edge_stopwords": False,
                    "reject_function_pos_unigrams": False,
                }
            }
            for filename in ("appsettings.development.yaml", "appsettings.yaml"):
                (root / filename).write_text(
                    yaml.safe_dump(payload),
                    encoding="utf-8",
                )
            reader = ConfigReader(config_dir=root, env_type="development")
            configurable = CandidateExtractionService(reader)
            processed = self.processor.process("در ۱۲ تحلیل")
            texts = {item.text for item in configurable.extract("doc", processed)}
            self.assertIn("در", texts)
            self.assertIn("۱۲", texts)
            self.assertIn("در ۱۲", texts)


if __name__ == "__main__":
    unittest.main()
