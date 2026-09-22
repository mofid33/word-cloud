from __future__ import annotations

import importlib
import inspect
import pkgutil

from fastapi import APIRouter, FastAPI

from src.infrastructure.di.inject import inject, resolve
from src.infrastructure.utils.config_reader import ConfigReader


@inject
class WebService:
    def __init__(self, config_reader: ConfigReader):
        self._config = config_reader

    def discover_controllers(
        self,
        package_name: str = "src.application",
    ) -> list[type]:
        package = importlib.import_module(package_name)
        paths = getattr(package, "__path__", None)
        if paths is None:
            return []

        controllers: list[type] = []
        for feature in pkgutil.iter_modules(paths):
            if not feature.ispkg or feature.name.startswith("_"):
                continue
            module_name = (
                f"{package_name}.{feature.name}."
                f"{feature.name}_controller"
            )
            try:
                module = importlib.import_module(module_name)
            except ModuleNotFoundError as exc:
                if exc.name == module_name:
                    continue
                raise

            expected_name = (
                "".join(part.title() for part in feature.name.split("_"))
                + "Controller"
            )
            controller = getattr(module, expected_name, None)
            if (
                inspect.isclass(controller)
                and controller.__name__.endswith("Controller")
            ):
                controllers.append(controller)
        return controllers

    def create_app(self) -> FastAPI:
        app = FastAPI(
            title=str(
                self._config.get(
                    "app.name",
                    "Persian Semantic Text Analytics Service",
                )
            ),
            version=str(self._config.get("app.version", "0.1.0")),
        )
        prefix = self._config.get_api_prefix()
        for controller_type in self.discover_controllers():
            controller = resolve(controller_type)
            router = controller.api()
            if not isinstance(router, APIRouter):
                raise TypeError(
                    f"{controller_type.__name__}.api() must return APIRouter"
                )
            feature = controller_type.__module__.split(".")[-2]
            app.include_router(
                router,
                prefix=f"{prefix}/{feature}",
            )
        return app
