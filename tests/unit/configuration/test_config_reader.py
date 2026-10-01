from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from src.infrastructure.utils.config_reader import ConfigReader


class ConfigReaderTests(unittest.TestCase):
    def test_development_selects_development_file(self) -> None:
        config = ConfigReader(env_type="development")

        self.assertEqual(config.environment, "development")
        self.assertEqual(
            config.source_path.name,
            "appsettings.development.yaml",
        )
        self.assertIsNotNone(config.get("database.url"))

    def test_production_selects_base_file_without_database_secret(self) -> None:
        config = ConfigReader(env_type="production")

        self.assertEqual(config.environment, "production")
        self.assertEqual(config.source_path.name, "appsettings.yaml")
        self.assertIsNone(config.get("database.url"))
        self.assertTrue(config.get("database.pool_pre_ping"))

    def test_runtime_configuration_contains_phase_five_sections(self) -> None:
        for environment in ("development", "production"):
            config = ConfigReader(env_type=environment)
            with self.subTest(environment=environment):
                self.assertIsNotNone(config.get("models.cache_dir"))
                self.assertIsInstance(
                    config.get("models.allow_remote_downloads"),
                    bool,
                )
                self.assertEqual(config.get("device.type"), "cpu")
                self.assertGreater(config.get("batch.default_size"), 0)
                self.assertGreaterEqual(
                    config.get("batch.max_size"),
                    config.get("batch.default_size"),
                )
                self.assertEqual(
                    config.get(
                        "analysis.limits.max_documents_per_analysis"
                    ),
                    5000,
                )
                self.assertEqual(
                    config.get("analysis.sync_threshold.max_documents"),
                    20,
                )
                self.assertEqual(
                    config.get("analysis_queue.backend"),
                    "postgres",
                )
                self.assertGreaterEqual(
                    config.get("analysis_queue.maximum_attempts"),
                    1,
                )
                self.assertGreater(
                    config.get("analysis_queue.visibility_timeout_seconds"),
                    config.get("analysis_queue.heartbeat_interval_seconds"),
                )
                self.assertGreater(
                    config.get("analysis_queue.recovery_batch_size"),
                    0,
                )
                self.assertEqual(
                    config.get("analysis_queue.transient_payload.backend"),
                    "redis",
                )
                self.assertGreaterEqual(
                    config.get("analysis_queue.transient_payload.ttl_seconds"),
                    60,
                )

    def test_non_development_environment_uses_production_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "appsettings.development.yaml").write_text(
                yaml.safe_dump({"marker": "development"}),
                encoding="utf-8",
            )
            (root / "appsettings.yaml").write_text(
                yaml.safe_dump({"marker": "base"}),
                encoding="utf-8",
            )

            config = ConfigReader(
                config_dir=root,
                env_type="production",
            )

        self.assertEqual(config.get("marker"), "base")

    def test_missing_required_value_raises_without_secret_value(self) -> None:
        config = ConfigReader(env_type="production")

        with self.assertRaisesRegex(
            KeyError,
            "database.url",
        ):
            config.require("database.url")


if __name__ == "__main__":
    unittest.main()
