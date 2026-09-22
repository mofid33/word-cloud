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

        route_paths = {
            route.path
            for route in app.routes
            if hasattr(route, "path")
        }
        self.assertIn("/api/v1/analysis/validate", route_paths)


if __name__ == "__main__":
    unittest.main()
