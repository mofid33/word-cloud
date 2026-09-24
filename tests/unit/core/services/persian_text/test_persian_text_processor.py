from __future__ import annotations

import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

from src.core.services.persian_text.persian_text_processor import PersianTextProcessor
from src.infrastructure.providers.persian_nlp.persian_nlp_resource_provider import (
    PersianNlpResourceProvider,
)
from src.infrastructure.utils.config_reader import ConfigReader


class PersianTextProcessorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._temp_dir = tempfile.TemporaryDirectory()
        root = Path(cls._temp_dir.name)
        resource_path = root / "resources.json"
        resource_path.write_text(
            json.dumps(
                {
                    "version": "test-1",
                    "general_stopwords": ["و", "در", "هوش"],
                    "domain_stopwords": {
                        "COURSE": ["جلسه"],
                        "MEDIA": ["خبر"],
                    },
                    "protected_terms": ["هوش مصنوعی"],
                    "synonyms": {
                        "AI": "هوش مصنوعی",
                        "ماشین لرنینگ": "یادگیری ماشین",
                    },
                    "canonical_terms": {
                        "داده کاوی": "داده‌کاوی",
                        "نرم افزار": "نرم‌افزار",
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        config = {
            "persian_nlp": {
                "resources": {"path": str(resource_path)},
                "lemmatization": {"enabled": True},
                "pos_processing": {"enabled": True},
            }
        }
        for filename in ("appsettings.development.yaml", "appsettings.yaml"):
            (root / filename).write_text(
                yaml.safe_dump(config, allow_unicode=True),
                encoding="utf-8",
            )
        reader = ConfigReader(config_dir=root, env_type="development")
        cls.processor = PersianTextProcessor(PersianNlpResourceProvider(reader))

    @classmethod
    def tearDownClass(cls) -> None:
        cls._temp_dir.cleanup()

    def test_unicode_arabic_yeh_kaf_and_diacritics(self) -> None:
        self.assertEqual(
            self.processor.normalize("  كِتاب يكى   ﷲ  "),
            "کتاب یکی الله",
        )

    def test_zwnj_and_whitespace_normalization(self) -> None:
        self.assertEqual(
            self.processor.normalize("می‌‌شود  خانه‌ ها ‌ کتاب"),
            "می‌شود خانه‌ها کتاب",
        )
        self.assertEqual(
            self.processor.normalize("الف\n\t  ب   ج"),
            "الف ب ج",
        )

    def test_noise_and_malformed_unicode(self) -> None:
        self.assertEqual(
            self.processor.normalize("سلام🙂\x00\ud800 دنیا"),
            "سلام دنیا",
        )

    def test_tokenization_mixed_persian_latin_numbers(self) -> None:
        self.assertEqual(
            self.processor.tokenize("نسخه GPT-4 در 2026/09 و عدد ١٢ است."),
            ("نسخه", "GPT", "4", "در", "2026", "09", "و", "عدد", "۱۲", "است"),
        )

    def test_stopwords_and_domain_stopwords_only_filter_embedding(self) -> None:
        general = self.processor.process("داده و تحلیل در سامانه")
        self.assertEqual(general.candidate_text, "داده و تحلیل در سامانه")
        self.assertEqual(general.embedding_text, "داده تحلیل سامانه")

        domain = self.processor.process("جلسه تحلیل داده", domain="COURSE")
        self.assertEqual(domain.embedding_text, "تحلیل داده")
        self.assertEqual(
            self.processor.process("جلسه تحلیل داده").embedding_text,
            "جلسه تحلیل داده",
        )

    def test_protected_term_wins_over_stopword_conflict(self) -> None:
        result = self.processor.process("هوش مصنوعی و داده")
        self.assertEqual(result.embedding_text, "هوش مصنوعی داده")
        self.assertTrue(result.candidate_tokens[0].is_protected)
        self.assertTrue(result.candidate_tokens[1].is_protected)
        self.assertFalse(result.candidate_tokens[0].is_stopword)

    def test_synonym_and_canonical_terms_are_deterministic(self) -> None:
        synonym = self.processor.process("AI کاربرد زیادی دارد")
        self.assertEqual(
            synonym.candidate_text,
            "هوش مصنوعی کاربرد زیادی دارد",
        )
        self.assertEqual(
            synonym.embedding_text,
            "هوش مصنوعی کاربرد زیادی دارد",
        )

        canonical = self.processor.process("داده کاوی و نرم افزار")
        self.assertEqual(
            canonical.candidate_text,
            "داده‌کاوی و نرم‌افزار",
        )
        self.assertEqual(
            canonical.embedding_text,
            "داده‌کاوی نرم‌افزار",
        )

    def test_candidate_and_embedding_representations_are_separate(self) -> None:
        result = self.processor.process("تحلیل داده، و مدل سازی.")
        self.assertEqual(result.candidate_text, "تحلیل داده و مدل سازی")
        self.assertEqual(
            [token.segment_index for token in result.candidate_tokens],
            [0, 0, 1, 1, 1],
        )
        self.assertEqual(result.embedding_text, "تحلیل داده مدل سازی")

    def test_configurable_lemmatization_and_pos_processing(self) -> None:
        result = self.processor.process("کتاب‌ها مدل‌های پژوهش‌ها")
        self.assertEqual(result.embedding_tokens, ("کتاب", "مدل", "پژوهش"))

        tagged = self.processor.process("من در ۱۲ پروژه می‌کنم GPT")
        self.assertEqual(
            [token.pos for token in tagged.candidate_tokens],
            ["PRON", "ADP", "NUM", "NOUN", "VERB", "LATIN"],
        )

    def test_repeated_and_concurrent_execution_is_deterministic(self) -> None:
        expected = self.processor.process("AI و داده کاوی", domain="COURSE")
        self.assertEqual(
            expected,
            self.processor.process("AI و داده کاوی", domain="COURSE"),
        )

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(
                executor.map(
                    lambda _: self.processor.process(
                        "AI و داده کاوی در مدل‌ها",
                        domain="COURSE",
                    ),
                    range(32),
                )
            )
        self.assertTrue(all(result == results[0] for result in results))

    def test_empty_whitespace_and_non_string_input(self) -> None:
        self.assertEqual(self.processor.process("").candidate_tokens, ())
        self.assertEqual(self.processor.process(" \n\t ").embedding_text, "")
        with self.assertRaisesRegex(TypeError, "text must be a string"):
            self.processor.normalize(None)  # type: ignore[arg-type]

    def test_resource_version_is_exposed(self) -> None:
        self.assertEqual(self.processor.process("داده").resource_version, "test-1")


if __name__ == "__main__":
    unittest.main()
