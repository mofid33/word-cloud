from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from src.infrastructure.context.vault.vault_service import VaultService
from src.infrastructure.di.inject import inject
from src.infrastructure.utils.config_reader import ConfigReader


class Base(DeclarativeBase):
    pass


@inject
class PsqlDbContext:
    __di_singleton__ = True

    def __init__(self, config_reader: ConfigReader, vault_service: VaultService):
        database_url = self.resolve_database_url(config_reader, vault_service)
        self._engine: AsyncEngine = create_async_engine(
            database_url,
            pool_pre_ping=bool(
                self._config_value(config_reader, "database.pool_pre_ping", True)
            ),
            pool_size=int(
                self._config_value(config_reader, "database.pool_size", 5)
            ),
            max_overflow=int(
                self._config_value(config_reader, "database.max_overflow", 10)
            ),
            pool_timeout=float(
                self._config_value(
                    config_reader,
                    "database.pool_timeout_seconds",
                    30,
                )
            ),
        )
        self._session_factory = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    @staticmethod
    def _config_value(
        config_reader: ConfigReader,
        key: str,
        default: Any,
    ) -> Any:
        getter = getattr(config_reader, "get", None)
        if getter is None:
            return default
        return getter(key, default)

    @staticmethod
    def normalize_database_url(url: str) -> str:
        value = url.strip()
        if not value:
            raise ValueError("Database URL must be non-empty")
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+asyncpg://", 1)
        return value

    @classmethod
    def resolve_database_url(
        cls,
        config_reader: ConfigReader,
        vault_service: VaultService,
    ) -> str:
        if vault_service.enabled:
            return cls.normalize_database_url(
                vault_service.get_secret("database_url")
            )

        environment_url = os.getenv("DATABASE_URL")
        if environment_url:
            return cls.normalize_database_url(environment_url)

        return cls.normalize_database_url(
            str(config_reader.require("database.url"))
        )

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self._session_factory() as session:
            yield session

    async def dispose_async(self) -> None:
        await self._engine.dispose()
