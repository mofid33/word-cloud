from __future__ import annotations

import unittest

from src.infrastructure.providers.runtime.runtime_settings import RuntimeSettings


class _Config:
    def __init__(self, environment="production", **overrides):
        self.environment = environment
        self.values = {
            "security": {
                "docs_enabled": False,
                "allowed_hosts": ["service.example"],
                "cors_allowed_origins": [],
            },
            "runtime": {
                "maximum_request_body_bytes": 12_000_000,
                "request_timeout_seconds": 300,
                "graceful_shutdown_seconds": 30,
            },
            "observability": {
                "logging": {"level": "INFO"},
                "metrics": {"enabled": True},
            },
        }
        self.values.update(overrides)

    def get(self, key, default=None):
        return self.values.get(key, default)


class RuntimeSettingsTests(unittest.TestCase):
    def test_production_settings_are_validated(self) -> None:
        settings = RuntimeSettings(_Config())
        self.assertFalse(settings.docs_enabled)
        self.assertEqual(settings.allowed_hosts, ("service.example",))
        self.assertEqual(settings.maximum_request_body_bytes, 12_000_000)
        self.assertEqual(settings.log_level, "INFO")

    def test_production_rejects_docs_and_wildcard_hosts(self) -> None:
        config = _Config()
        config.values["security"] = {
            "docs_enabled": True,
            "allowed_hosts": ["*"],
            "cors_allowed_origins": [],
        }
        with self.assertRaises(ValueError):
            RuntimeSettings(config)

    def test_development_allows_wildcard_host(self) -> None:
        config = _Config(environment="development")
        config.values["security"] = {
            "docs_enabled": True,
            "allowed_hosts": ["*"],
            "cors_allowed_origins": [],
        }
        settings = RuntimeSettings(config)
        self.assertTrue(settings.docs_enabled)


if __name__ == "__main__":
    unittest.main()
