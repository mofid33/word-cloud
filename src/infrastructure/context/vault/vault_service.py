from __future__ import annotations

import os

from src.infrastructure.di.inject import inject
from src.infrastructure.utils.config_reader import ConfigReader


@inject
class VaultService:
    __di_singleton__ = True

    def __init__(self, config_reader: ConfigReader):
        self._config = config_reader

    @property
    def enabled(self) -> bool:
        return bool(self._config.get("vault.enabled", False))

    def get_secret(self, name: str) -> str:
        if not name or not name.strip():
            raise ValueError("Secret name must be non-empty")
        env_name = f"VAULT_{name.strip().upper()}"
        value = os.getenv(env_name)
        if value is None:
            raise KeyError(f"Secret is unavailable: {name}")
        return value
