import unittest

from src.application.web import WebService
from src.infrastructure.di.bootstrap import bootstrap_di
from src.infrastructure.di.inject import resolve
from src.infrastructure.utils.config_reader import ConfigReader


class AnalysisDiscoveryTests(unittest.TestCase):
    def test_analysis_controller_is_discovered_and_mounted(self) -> None:
        bootstrap_di()
        web = WebService(resolve(ConfigReader))
        controller_names = {
            controller.__name__
            for controller in web.discover_controllers()
        }
        self.assertIn("AnalysisController", controller_names)

        app = web.create_app()
        paths = {route.path for route in app.routes}
        self.assertIn("/api/v1/analysis/validate", paths)


if __name__ == "__main__":
    unittest.main()
