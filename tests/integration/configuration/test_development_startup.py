from __future__ import annotations

import unittest

from fastapi import FastAPI

from src.application.web import WebService
from src.infrastructure.di.bootstrap import bootstrap_di
from src.infrastructure.utils.config_reader import ConfigReader


class DevelopmentStartupTests(unittest.TestCase):
    def test_application_builds_with_development_configuration(self) -> None:
        bootstrap_di()
        config = ConfigReader(env_type="development")
        app = WebService(config).create_app()

        self.assertIsInstance(app, FastAPI)
        self.assertEqual(
            app.title,
            "Persian Semantic Text Analytics Service",
        )

        openapi_paths = app.openapi()["paths"]
        self.assertIn("/api/v1/analysis/validate", openapi_paths)
        self.assertIn(
            "post",
            openapi_paths["/api/v1/analysis/validate"],
        )


if __name__ == "__main__":
    unittest.main()
