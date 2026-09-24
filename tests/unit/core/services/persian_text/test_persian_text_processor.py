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
                    "general_stopwords": ["و", "در", "هوش", "سامانه"],
                    "domain_stopwords": {
                        "COURSE": ["جلسه"],
                        "MEDIA": ["خبر"],
                    },
                    "protected_terms": [
                        "هوش مصنوعی",
                        "مدل‌های ویژه",
                        "سامانه ملی",
                    ],
                    "synonyms": {
                        "AI": "هوش مصنوعی",
                        "ماشین لرنینگ": "یادگیری ماشین",
                        "پلتفرم ملی": "سامانه ملی",
                    },
                    "canonical_terms": {
                        "داده کاوی": "داده‌کاوی",
                        "نرم افزار": "نرم‌افزار",
                        "سامانه کشوری": "سامانه ملی",
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
                "embedding": {
                    "remove_stopwords": True,
                    "use_lemmas": True,
                },
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
            self.processor.tokenize(
                "نسخه GPT-4 در 2026/09 و BERT-base عدد ١٢ است."
            ),
            (
                "نسخه",
                "GPT-4",
                "در",
                "2026/09",
                "و",
                "BERT-base",
                "عدد",
                "۱۲",
                "است",
            ),
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
            ["PRON", "ADP", "NUM", "X", "VERB", "LATIN"],
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


    def test_lemmatization_is_conservative_for_non_plural_words(self) -> None:
        result = self.processor.process("اژدها منتها کتاب‌ها")
        self.assertEqual(
            [token.lemma for token in result.candidate_tokens],
            ["اژدها", "منتها", "کتاب"],
        )

    def test_protected_terms_are_not_lemmatized(self) -> None:
        result = self.processor.process("مدل‌های ویژه")
        self.assertTrue(
            all(token.is_protected for token in result.candidate_tokens)
        )
        self.assertEqual(
            [token.lemma for token in result.candidate_tokens],
            ["مدل‌های", "ویژه"],
        )

    def test_pos_processing_uses_unknown_instead_of_guessing_noun(self) -> None:
        result = self.processor.process("رفت رفتند زیبا پروژه")
        self.assertEqual(
            [token.pos for token in result.candidate_tokens],
            ["VERB", "VERB", "X", "X"],
        )

    def test_mapping_targets_become_protected_before_stopword_filtering(self) -> None:
        synonym = self.processor.process("پلتفرم ملی و داده")
        canonical = self.processor.process("سامانه کشوری و داده")
        self.assertEqual(synonym.embedding_text, "سامانه ملی داده")
        self.assertEqual(canonical.embedding_text, "سامانه ملی داده")
        self.assertTrue(synonym.candidate_tokens[0].is_protected)
        self.assertTrue(canonical.candidate_tokens[0].is_protected)

    def test_disabled_linguistic_processing_and_embedding_filters(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            resource_path = root / "resources.json"
            resource_path.write_text(
                json.dumps(
                    {
                        "version": "test-disabled",
                        "general_stopwords": ["و"],
                        "domain_stopwords": {},
                        "protected_terms": [],
                        "synonyms": {},
                        "canonical_terms": {},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            config = {
                "persian_nlp": {
                    "resources": {"path": str(resource_path)},
                    "lemmatization": {"enabled": False},
                    "pos_processing": {"enabled": False},
                    "embedding": {
                        "remove_stopwords": False,
                        "use_lemmas": False,
                    },
                }
            }
            for filename in ("appsettings.development.yaml", "appsettings.yaml"):
                (root / filename).write_text(
                    yaml.safe_dump(config, allow_unicode=True),
                    encoding="utf-8",
                )
            processor = PersianTextProcessor(
                PersianNlpResourceProvider(
                    ConfigReader(config_dir=root, env_type="development")
                )
            )

            result = processor.process("کتاب‌ها و داده")
            self.assertEqual(
                [token.lemma for token in result.candidate_tokens],
                ["کتاب‌ها", "و", "داده"],
            )
            self.assertTrue(
                all(token.pos is None for token in result.candidate_tokens)
            )
            self.assertEqual(
                result.embedding_tokens,
                ("کتاب‌ها", "و", "داده"),
            )


if __name__ == "__main__":
    unittest.main()
