from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from src.infrastructure.di.inject import inject


@inject
class ConfigReader:
    __di_singleton__ = True

    def __init__(self, config_dir: Path | None = None, env_type: str | None = None):
        self._config_dir = config_dir or (
            Path(__file__).resolve().parents[2] / "host" / "res"
        )
        self._env_type = (env_type or os.getenv("ENV_TYPE", "development")).strip().lower()
        filename = (
            "appsettings.development.yaml"
            if self._env_type == "development"
            else "appsettings.yaml"
        )
        self._path = self._config_dir / filename
        if not self._path.is_file():
            raise FileNotFoundError(f"Configuration file not found: {self._path}")
        with self._path.open("r", encoding="utf-8") as stream:
            loaded = yaml.safe_load(stream) or {}
        if not isinstance(loaded, dict):
            raise ValueError(f"Configuration root must be a mapping: {self._path}")
        self._data = loaded

    @property
    def environment(self) -> str:
        return self._env_type

    @property
    def source_path(self) -> Path:
        return self._path

    def get(self, key: str, default: Any = None) -> Any:
        current: Any = self._data
        for part in key.split("."):
            if not isinstance(current, dict) or part not in current:
                return default
            current = current[part]
        return current

    def require(self, key: str) -> Any:
        value = self.get(key)
        if value is None:
            raise KeyError(f"Required configuration key is missing: {key}")
        return value

    def get_api_prefix(self) -> str:
        prefix = str(self.get("api.prefix", "/api/v1"))
        return "/" + prefix.strip("/")
