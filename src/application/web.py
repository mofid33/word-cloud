from __future__ import annotations

import asyncio
import importlib
import inspect
import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path
from time import monotonic
from uuid import uuid4

from fastapi import APIRouter, FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from src.infrastructure.context.sql_db.psql_dbcontext import PsqlDbContext
from src.infrastructure.di.inject import inject
from src.infrastructure.observability.logging_config import request_id_context
from src.infrastructure.observability.tracing import (
    span_id_context,
    start_server_trace,
    trace_id_context,
)
from src.infrastructure.observability.metrics_service import MetricsService
from src.infrastructure.providers.analysis_queue.redis_analysis_transient_payload_store import RedisAnalysisTransientPayloadStore
from src.infrastructure.providers.runtime.runtime_settings import RuntimeSettings
from src.infrastructure.utils.config_reader import ConfigReader


_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


@inject
class WebService:
    def __init__(
        self,
        config_reader: ConfigReader,
        runtime_settings: RuntimeSettings,
        metrics: MetricsService,
        db_context: PsqlDbContext,
        transient_store: RedisAnalysisTransientPayloadStore,
    ):
        self._config = config_reader
        self._runtime = runtime_settings
        self._metrics = metrics
        self._db = db_context
        self._transient_store = transient_store
        self._logger = logging.getLogger("word_cloud.http")

    def discover_controllers(self, package_name: str = "src.application") -> list[type]:
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
                controller_file = feature_path / f"{feature_name}_controller.py"
                if not controller_file.is_file():
                    continue
                module_name = f"{package_name}.{feature_name}.{feature_name}_controller"
                if module_name in imported_modules:
                    continue
                module = importlib.import_module(module_name)
                imported_modules.add(module_name)
                expected_name = "".join(part.title() for part in feature_name.split("_")) + "Controller"
                controller = getattr(module, expected_name, None)
                if inspect.isclass(controller) and controller.__name__.endswith("Controller"):
                    controllers.append(controller)
        return controllers

    def create_app(self) -> FastAPI:
        @asynccontextmanager
        async def lifespan(_app: FastAPI):
            yield
            self._logger.info(
                "application_shutdown_started",
                extra={"event": "application_shutdown_started"},
            )
            await self._transient_store.close_async()
            await self._db.dispose_async()
            self._logger.info(
                "application_shutdown_complete",
                extra={"event": "application_shutdown_complete"},
            )

        docs_url = "/docs" if self._runtime.docs_enabled else None
        openapi_url = "/openapi.json" if self._runtime.docs_enabled else None
        app = FastAPI(
            title=str(self._config.get("app.name", "Persian Semantic Text Analytics Service")),
            version=str(self._config.get("app.version", "0.1.0")),
            docs_url=docs_url,
            redoc_url=None,
            openapi_url=openapi_url,
            lifespan=lifespan,
        )
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(self._runtime.allowed_hosts))
        if self._runtime.cors_allowed_origins:
            app.add_middleware(
                CORSMiddleware,
                allow_origins=list(self._runtime.cors_allowed_origins),
                allow_methods=["GET", "POST"],
                allow_headers=["Content-Type", "X-Request-ID", "traceparent"],
                expose_headers=["X-Request-ID", "traceparent"],
                allow_credentials=False,
            )

        @app.middleware("http")
        async def production_middleware(request: Request, call_next):
            def apply_security_headers(response, request_id: str, traceparent: str):
                response.headers["X-Request-ID"] = request_id
                response.headers["traceparent"] = traceparent
                response.headers["X-Content-Type-Options"] = "nosniff"
                response.headers["X-Frame-Options"] = "DENY"
                response.headers["Referrer-Policy"] = "no-referrer"
                response.headers["Cache-Control"] = "no-store"
                return response

            header = request.headers.get("x-request-id", "")
            request_id = header if _REQUEST_ID_PATTERN.fullmatch(header) else uuid4().hex
            trace = start_server_trace(request.headers.get("traceparent"))
            request_token = request_id_context.set(request_id)
            trace_token = trace_id_context.set(trace.trace_id)
            span_token = span_id_context.set(trace.span_id)
            started = monotonic()
            status_code = 500
            try:
                content_length = request.headers.get("content-length")
                if content_length:
                    try:
                        size = int(content_length)
                    except ValueError:
                        response = JSONResponse(status_code=400, content={"detail": {"code": "invalid_content_length", "message": "Invalid Content-Length header"}})
                        status_code = response.status_code
                        return apply_security_headers(response, request_id, trace.traceparent)
                    if size > self._runtime.maximum_request_body_bytes:
                        response = JSONResponse(status_code=413, content={"detail": {"code": "request_body_too_large", "message": "Request body exceeds the configured limit"}})
                        status_code = response.status_code
                        return apply_security_headers(response, request_id, trace.traceparent)
                if request.method in {"POST", "PUT", "PATCH"}:
                    body = await request.body()
                    if len(body) > self._runtime.maximum_request_body_bytes:
                        response = JSONResponse(status_code=413, content={"detail": {"code": "request_body_too_large", "message": "Request body exceeds the configured limit"}})
                        status_code = response.status_code
                        return apply_security_headers(response, request_id, trace.traceparent)
                try:
                    async with asyncio.timeout(self._runtime.request_timeout_seconds):
                        response = await call_next(request)
                except TimeoutError:
                    response = JSONResponse(status_code=504, content={"detail": {"code": "request_timeout", "message": "Request processing timed out"}})
                status_code = response.status_code
                return apply_security_headers(response, request_id, trace.traceparent)
            finally:
                elapsed = monotonic() - started
                route = getattr(request.scope.get("route"), "path", "unresolved")
                self._metrics.observe_http(method=request.method, route=str(route), status_code=status_code, duration_seconds=elapsed)
                self._logger.info(
                    "http_request_completed",
                    extra={"event": "http_request_completed", "method": request.method, "route": str(route), "status_code": status_code, "duration_ms": round(elapsed * 1000, 3)},
                )
                span_id_context.reset(span_token)
                trace_id_context.reset(trace_token)
                request_id_context.reset(request_token)

        @app.exception_handler(RequestValidationError)
        async def request_validation_error_handler(_request: Request, _exc: RequestValidationError) -> JSONResponse:
            return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, content={"detail": {"code": "request_validation_error", "message": "Request payload validation failed"}})

        @app.exception_handler(Exception)
        async def unhandled_error_handler(_request: Request, exc: Exception) -> JSONResponse:
            self._logger.exception("unhandled_request_error", extra={"event": "unhandled_request_error", "error_code": "internal_server_error"}, exc_info=exc)
            return JSONResponse(status_code=500, content={"detail": {"code": "internal_server_error", "message": "Internal server error"}})

        prefix = self._config.get_api_prefix()
        for controller_type in self.discover_controllers():
            controller = controller_type()
            router = controller.api()
            if not isinstance(router, APIRouter):
                raise TypeError(f"{controller_type.__name__}.api() must return APIRouter")
            feature = controller_type.__module__.split(".")[-2]
            app.include_router(router, prefix=f"{prefix}/{feature}")
        return app
