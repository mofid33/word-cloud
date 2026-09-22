from __future__ import annotations

import importlib
import inspect
from pathlib import Path

from fastapi import APIRouter, FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.infrastructure.di.inject import inject
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
        package_paths = getattr(package, "__path__", None)
        if package_paths is None:
            return []

        controllers: list[type] = []
        imported_modules: set[str] = set()

        for package_path in sorted(str(path) for path in package_paths):
            root = Path(package_path)
            if not root.is_dir():
                continue

            for feature_path in sorted(root.iterdir(), key=lambda path: path.name):
                if not feature_path.is_dir() or feature_path.name.startswith("_"):
                    continue

                feature_name = feature_path.name
                controller_file = (
                    feature_path / f"{feature_name}_controller.py"
                )
                if not controller_file.is_file():
                    continue

                module_name = (
                    f"{package_name}.{feature_name}."
                    f"{feature_name}_controller"
                )
                if module_name in imported_modules:
                    continue

                module = importlib.import_module(module_name)
                imported_modules.add(module_name)

                expected_name = (
                    "".join(
                        part.title()
                        for part in feature_name.split("_")
                    )
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

        @app.exception_handler(RequestValidationError)
        async def request_validation_error_handler(
            _request: Request,
            _exc: RequestValidationError,
        ) -> JSONResponse:
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                content={
                    "detail": {
                        "code": "request_validation_error",
                        "message": "Request payload validation failed",
                    }
                },
            )

        prefix = self._config.get_api_prefix()
        for controller_type in self.discover_controllers():
            controller = controller_type()
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
