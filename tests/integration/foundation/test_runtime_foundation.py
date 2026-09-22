import importlib
import sys
import tempfile
import unittest
from pathlib import Path

from src.application.web import WebService
from src.infrastructure.di.inject import (
    DependencyResolutionError,
    reset_di_state,
    resolve,
)
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

    def test_discovery_skips_broken_module_and_continues(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package = root / "fixture_discovery"
            package.mkdir()
            (package / "__init__.py").write_text("", encoding="utf-8")
            (package / "broken.py").write_text(
                "raise RuntimeError('broken module')\n",
                encoding="utf-8",
            )
            (package / "provider.py").write_text(
                "from src.infrastructure.di.inject import inject\n"
                "@inject\n"
                "class HealthyProvider:\n"
                "    pass\n",
                encoding="utf-8",
            )

            sys.path.insert(0, temp_dir)
            try:
                imported = import_discoverable_modules(
                    ("fixture_discovery",)
                )
                self.assertIn("fixture_discovery.provider", imported)
                self.assertNotIn("fixture_discovery.broken", imported)
            finally:
                sys.path.remove(temp_dir)
                for key in list(sys.modules):
                    if key.startswith("fixture_discovery"):
                        sys.modules.pop(key, None)
                reset_di_state()

    def test_cached_discovery_restores_registry_after_reset(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package = root / "fixture_cached"
            package.mkdir()
            (package / "__init__.py").write_text("", encoding="utf-8")
            (package / "provider.py").write_text(
                "from abc import ABC, abstractmethod\n"
                "from src.infrastructure.di.inject import inject\n"
                "class Provider(ABC):\n"
                "    @abstractmethod\n"
                "    def value(self):\n"
                "        raise NotImplementedError\n"
                "@inject\n"
                "class ConcreteProvider(Provider):\n"
                "    def value(self):\n"
                "        return 'ok'\n",
                encoding="utf-8",
            )

            sys.path.insert(0, temp_dir)
            try:
                import_discoverable_modules(("fixture_cached",))
                module = importlib.import_module("fixture_cached.provider")
                self.assertEqual(resolve(module.Provider).value(), "ok")

                reset_di_state()
                with self.assertRaises(DependencyResolutionError):
                    resolve(module.Provider)

                imported = import_discoverable_modules(("fixture_cached",))
                self.assertIn("fixture_cached.provider", imported)
                self.assertEqual(resolve(module.Provider).value(), "ok")
            finally:
                sys.path.remove(temp_dir)
                for key in list(sys.modules):
                    if key.startswith("fixture_cached"):
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
