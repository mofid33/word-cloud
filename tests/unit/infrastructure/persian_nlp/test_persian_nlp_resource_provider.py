from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import yaml

from src.infrastructure.providers.persian_nlp.persian_nlp_resource_provider import (
    PersianNlpResourceProvider,
)
from src.infrastructure.utils.config_reader import ConfigReader


class PersianNlpResourceProviderTests(unittest.TestCase):
    def _config(self, root: Path, resource_path: Path) -> ConfigReader:
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
        return ConfigReader(config_dir=root, env_type="development")

    def test_resources_are_deterministic_immutable_and_configured(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            resource_path = root / "resources.json"
            resource_path.write_text(
                json.dumps(
                    {
                        "version": "v1",
                        "general_stopwords": ["و", "در", "و"],
                        "domain_stopwords": {"course": ["درس", "درس"]},
                        "protected_terms": ["هوش مصنوعی"],
                        "synonyms": {"AI": "هوش مصنوعی"},
                        "canonical_terms": {"داده کاوی": "داده‌کاوی"},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            provider = PersianNlpResourceProvider(
                self._config(root, resource_path)
            )

            resources = provider.resources
            self.assertEqual(resources.version, "v1")
            self.assertEqual(resources.general_stopwords, frozenset({"و", "در"}))
            self.assertEqual(
                resources.domain_stopwords["COURSE"],
                frozenset({"درس"}),
            )
            self.assertTrue(resources.lemmatization_enabled)
            self.assertTrue(resources.pos_processing_enabled)
            with self.assertRaises(TypeError):
                resources.synonyms["x"] = "y"  # type: ignore[index]

    def test_invalid_resource_fails_without_raw_text_context(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            resource_path = root / "resources.json"
            resource_path.write_text("{}", encoding="utf-8")
            config = self._config(root, resource_path)

            with self.assertRaisesRegex(ValueError, "resource 'version'"):
                PersianNlpResourceProvider(config)


if __name__ == "__main__":
    unittest.main()
