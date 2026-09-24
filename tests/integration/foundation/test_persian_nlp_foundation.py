from __future__ import annotations

import unittest

from src.core.services.persian_text.persian_text_processor import PersianTextProcessor
from src.infrastructure.di.bootstrap import bootstrap_di
from src.infrastructure.di.inject import reset_di_state, resolve
from src.infrastructure.providers.persian_nlp.persian_nlp_resource_provider import (
    PersianNlpResourceProvider,
)


class PersianNlpFoundationIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_di_state()
        bootstrap_di()

    def test_processor_and_resource_provider_are_resolved_by_discovery(self) -> None:
        processor = resolve(PersianTextProcessor)
        first_provider = resolve(PersianNlpResourceProvider)
        second_provider = resolve(PersianNlpResourceProvider)

        self.assertIsInstance(processor, PersianTextProcessor)
        self.assertIs(first_provider, second_provider)

        result = processor.process("كِتاب‌ها و داده کاوی", domain="COURSE")
        self.assertEqual(result.normalized_text, "کتاب‌ها و داده کاوی")
        self.assertEqual(
            result.embedding_tokens,
            ("کتاب‌ها", "و", "داده‌کاوی"),
        )
        self.assertEqual(result.candidate_tokens[0].lemma, "کتاب")


if __name__ == "__main__":
    unittest.main()
