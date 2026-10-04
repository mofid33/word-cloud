from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from src.infrastructure.di.inject import inject
from src.infrastructure.utils.config_reader import ConfigReader


@inject
@dataclass(frozen=True, init=False)
class RuntimeSettings:
    __di_singleton__ = True

    environment: str
    docs_enabled: bool
    allowed_hosts: tuple[str, ...]
    cors_allowed_origins: tuple[str, ...]
    maximum_request_body_bytes: int
    request_timeout_seconds: float
    graceful_shutdown_seconds: float
    log_level: str
    metrics_enabled: bool

    def __init__(self, config_reader: ConfigReader):
        security = config_reader.get("security", {})
        runtime = config_reader.get("runtime", {})
        observability = config_reader.get("observability", {})
        if not isinstance(security, dict) or not isinstance(runtime, dict) or not isinstance(observability, dict):
            raise ValueError("security, runtime and observability configuration must be mappings")

        docs_enabled = self._boolean(security, "docs_enabled")
        allowed_hosts = self._string_list(security, "allowed_hosts")
        cors_allowed_origins = self._string_list(security, "cors_allowed_origins")
        allowed_hosts_override = os.getenv("ALLOWED_HOSTS")
        if allowed_hosts_override is not None:
            allowed_hosts = self._csv(allowed_hosts_override, "ALLOWED_HOSTS")
        cors_override = os.getenv("CORS_ALLOWED_ORIGINS")
        if cors_override is not None and cors_override.strip():
            cors_allowed_origins = self._csv(cors_override, "CORS_ALLOWED_ORIGINS")
        maximum_request_body_bytes = self._integer(runtime, "maximum_request_body_bytes", 1024, 100_000_000)
        request_timeout_seconds = self._number(runtime, "request_timeout_seconds", 1.0, 3600.0)
        graceful_shutdown_seconds = self._number(runtime, "graceful_shutdown_seconds", 1.0, 300.0)

        logging_config = observability.get("logging")
        metrics_config = observability.get("metrics")
        if not isinstance(logging_config, dict) or not isinstance(metrics_config, dict):
            raise ValueError("observability.logging and observability.metrics must be mappings")
        configured_log_level = str(logging_config.get("level", "")).strip().upper()
        log_level_override = os.getenv("LOG_LEVEL")
        log_level = (
            log_level_override.strip().upper()
            if log_level_override is not None
            else configured_log_level
        )
        if log_level not in logging._nameToLevel:
            raise ValueError("LOG_LEVEL or observability.logging.level is invalid")
        metrics_enabled = self._boolean(metrics_config, "enabled")

        if config_reader.environment != "development":
            if docs_enabled:
                raise ValueError("security.docs_enabled must be false outside development")
            if not allowed_hosts or "*" in allowed_hosts:
                raise ValueError("security.allowed_hosts must be explicit outside development")
            if "*" in cors_allowed_origins:
                raise ValueError("security.cors_allowed_origins cannot contain '*' outside development")

        object.__setattr__(self, "environment", config_reader.environment)
        object.__setattr__(self, "docs_enabled", docs_enabled)
        object.__setattr__(self, "allowed_hosts", allowed_hosts)
        object.__setattr__(self, "cors_allowed_origins", cors_allowed_origins)
        object.__setattr__(self, "maximum_request_body_bytes", maximum_request_body_bytes)
        object.__setattr__(self, "request_timeout_seconds", request_timeout_seconds)
        object.__setattr__(self, "graceful_shutdown_seconds", graceful_shutdown_seconds)
        object.__setattr__(self, "log_level", log_level)
        object.__setattr__(self, "metrics_enabled", metrics_enabled)

    @staticmethod
    def _boolean(mapping: dict, key: str) -> bool:
        value = mapping.get(key)
        if not isinstance(value, bool):
            raise ValueError(f"{key} must be a boolean")
        return value

    @staticmethod
    def _string_list(mapping: dict, key: str) -> tuple[str, ...]:
        value = mapping.get(key)
        if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
            raise ValueError(f"{key} must be a list of non-empty strings")
        return tuple(item.strip() for item in value)

    @staticmethod
    def _csv(value: str, key: str) -> tuple[str, ...]:
        items = tuple(item.strip() for item in value.split(",") if item.strip())
        if not items:
            raise ValueError(f"{key} must contain at least one value")
        return items

    @staticmethod
    def _integer(mapping: dict, key: str, minimum: int, maximum: int) -> int:
        value = mapping.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
            raise ValueError(f"{key} must be an integer between {minimum} and {maximum}")
        return value

    @staticmethod
    def _number(mapping: dict, key: str, minimum: float, maximum: float) -> float:
        value = mapping.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{key} must be a number")
        number = float(value)
        if not minimum <= number <= maximum:
            raise ValueError(f"{key} must be between {minimum} and {maximum}")
        return number
