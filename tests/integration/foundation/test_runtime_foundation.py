import importlib
import sys
import tempfile
import unittest
from pathlib import Path

from src.application.web import WebService
from src.infrastructure.di.inject import reset_di_state
from src.infrastructure.di.reflection import import_discoverable_modules
from src.infrastructure.utils.config_reader import ConfigReader


class RuntimeFoundationIntegrationTests(unittest.TestCase):
    def test_di_module_discovery_imports_injected_provider(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package = root / "fixture_infrastructure"
            package.mkdir()
            (package / "__init__.py").write_text("", encoding="utf-8")
            (package / "provider.py").write_text(
                "from src.infrastructure.di.inject import inject\n"
                "@inject\n"
                "class SampleProvider:\n"
                "    pass\n",
                encoding="utf-8",
            )
            sys.path.insert(0, temp_dir)
            try:
                imported = import_discoverable_modules(
                    ("fixture_infrastructure",)
                )
                self.assertIn(
                    "fixture_infrastructure.provider",
                    imported,
                )
            finally:
                sys.path.remove(temp_dir)
                for key in list(sys.modules):
                    if key.startswith("fixture_infrastructure"):
                        sys.modules.pop(key, None)
                reset_di_state()

    def test_webservice_discovers_convention_controller(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            app_pkg = root / "fixture_application"
            feature_pkg = app_pkg / "sample_feature"
            feature_pkg.mkdir(parents=True)
            (app_pkg / "__init__.py").write_text("", encoding="utf-8")
            (feature_pkg / "__init__.py").write_text("", encoding="utf-8")
            (feature_pkg / "sample_feature_controller.py").write_text(
                "from fastapi import APIRouter\n"
                "class SampleFeatureController:\n"
                "    def api(self):\n"
                "        return APIRouter()\n",
                encoding="utf-8",
            )
            config_dir = root / "config"
            config_dir.mkdir()
            (config_dir / "appsettings.development.yaml").write_text(
                "api:\n  prefix: /api/v1\n",
                encoding="utf-8",
            )
            sys.path.insert(0, temp_dir)
            try:
                importlib.invalidate_caches()
                service = WebService(
                    ConfigReader(
                        config_dir=config_dir,
                        env_type="development",
                    )
                )
                controllers = service.discover_controllers(
                    "fixture_application"
                )
                self.assertEqual(
                    [item.__name__ for item in controllers],
                    ["SampleFeatureController"],
                )
            finally:
                sys.path.remove(temp_dir)
                for key in list(sys.modules):
                    if key.startswith("fixture_application"):
                        sys.modules.pop(key, None)


if __name__ == "__main__":
    unittest.main()
