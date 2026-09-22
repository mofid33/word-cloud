import tempfile
import unittest
from pathlib import Path

from src.core.services.analysis.providers.analysis_queue_provider import (
    AnalysisQueueProvider,
)
from src.core.services.semantic.providers.embedding_provider import (
    EmbeddingProvider,
)
from src.core.services.semantic.providers.reranker_provider import (
    RerankerProvider,
)
from src.core.services.topic.providers.topic_model_provider import (
    TopicModelProvider,
)
from src.infrastructure.utils.config_reader import ConfigReader


class FoundationContractTests(unittest.TestCase):
    def test_config_reader_uses_environment_file_and_dotted_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "appsettings.development.yaml").write_text(
                "api:\n  prefix: /custom\n",
                encoding="utf-8",
            )
            reader = ConfigReader(
                config_dir=root,
                env_type="development",
            )
            self.assertEqual(reader.get_api_prefix(), "/custom")
            self.assertEqual(
                reader.get("missing", "fallback"),
                "fallback",
            )

    def test_replaceable_provider_contracts_are_abstract(self) -> None:
        for provider in (
            EmbeddingProvider,
            RerankerProvider,
            TopicModelProvider,
            AnalysisQueueProvider,
        ):
            with self.subTest(provider=provider.__name__):
                self.assertTrue(bool(provider.__abstractmethods__))


if __name__ == "__main__":
    unittest.main()
