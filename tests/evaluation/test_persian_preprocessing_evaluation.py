from __future__ import annotations

import json
import unittest
from pathlib import Path

from src.core.services.persian_text.persian_text_processor import PersianTextProcessor
from src.infrastructure.providers.persian_nlp.persian_nlp_resource_provider import (
    PersianNlpResourceProvider,
)
from src.infrastructure.utils.config_reader import ConfigReader


class PersianPreprocessingEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        config = ConfigReader(env_type="development")
        cls.processor = PersianTextProcessor(PersianNlpResourceProvider(config))
        fixture_path = (
            Path(__file__).resolve().parent
            / "fixtures"
            / "persian_preprocessing_cases.json"
        )
        cls.cases = json.loads(fixture_path.read_text(encoding="utf-8"))

    def test_real_persian_preprocessing_regression_fixture(self) -> None:
        for case in self.cases:
            with self.subTest(case=case["name"]):
                result = self.processor.process(
                    case["input"],
                    domain=case["domain"],
                )
                self.assertEqual(result.normalized_text, case["normalized"])
                self.assertEqual(
                    [token.text for token in result.candidate_tokens],
                    case["candidate_tokens"],
                )
                self.assertEqual(
                    list(result.embedding_tokens),
                    case["embedding_tokens"],
                )


if __name__ == "__main__":
    unittest.main()
