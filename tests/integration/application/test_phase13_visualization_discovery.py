import unittest

from src.application.web import WebService
from src.infrastructure.di.bootstrap import bootstrap_di
from src.infrastructure.di.inject import resolve
from src.infrastructure.utils.config_reader import ConfigReader


class Phase13VisualizationDiscoveryTests(unittest.TestCase):
    def test_visualization_controller_is_discovered_and_mounted(self) -> None:
        bootstrap_di()
        web = WebService(resolve(ConfigReader))
        controller_names = {
            controller.__name__
            for controller in web.discover_controllers()
        }
        self.assertIn("VisualizationController", controller_names)

        app = web.create_app()
        openapi_paths = app.openapi()["paths"]
        self.assertIn("/api/v1/visualization/{analysis_id}", openapi_paths)
        self.assertIn(
            "get",
            openapi_paths["/api/v1/visualization/{analysis_id}"],
        )
        self.assertIn(
            "/api/v1/visualization/{analysis_id}/topics/{topic_id}",
            openapi_paths,
        )
        self.assertIn(
            "get",
            openapi_paths[
                "/api/v1/visualization/{analysis_id}/topics/{topic_id}"
            ],
        )


if __name__ == "__main__":
    unittest.main()
