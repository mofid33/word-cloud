from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from src.infrastructure.scripts import run_migrations

from src.infrastructure.context.sql_db.psql_dbcontext import PsqlDbContext
from src.infrastructure.context.vault.vault_service import VaultService


class _Config:
    def __init__(self, *, vault_enabled: bool, database_url: str | None = None):
        self._vault_enabled = vault_enabled
        self._database_url = database_url

    def get(self, key: str, default=None):
        if key == "vault.enabled":
            return self._vault_enabled
        return default

    def require(self, key: str):
        if key != "database.url" or self._database_url is None:
            raise KeyError(key)
        return self._database_url


class SecretResolutionTests(unittest.TestCase):
    def test_vault_service_reads_named_secret_without_exposing_value(self) -> None:
        config = _Config(vault_enabled=True)
        vault = VaultService(config)

        with patch.dict(
            os.environ,
            {"VAULT_DATABASE_URL": "postgresql://user:secret@db/app"},
            clear=False,
        ):
            self.assertEqual(
                vault.get_secret("database_url"),
                "postgresql://user:secret@db/app",
            )

    def test_database_url_uses_vault_when_enabled(self) -> None:
        config = _Config(
            vault_enabled=True,
            database_url="postgresql://config/config",
        )
        vault = VaultService(config)

        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql://environment/environment",
                "VAULT_DATABASE_URL": "postgresql://vault/vault",
            },
            clear=False,
        ):
            resolved = PsqlDbContext.resolve_database_url(config, vault)

        self.assertEqual(
            resolved,
            "postgresql+asyncpg://vault/vault",
        )

    def test_database_url_uses_environment_override_when_vault_disabled(self) -> None:
        config = _Config(
            vault_enabled=False,
            database_url="postgresql://config/config",
        )
        vault = VaultService(config)

        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://environment/environment"},
            clear=False,
        ):
            resolved = PsqlDbContext.resolve_database_url(config, vault)

        self.assertEqual(
            resolved,
            "postgresql+asyncpg://environment/environment",
        )

    def test_database_url_falls_back_to_development_configuration(self) -> None:
        config = _Config(
            vault_enabled=False,
            database_url="postgresql://config/config",
        )
        vault = VaultService(config)

        with patch.dict(os.environ, {}, clear=True):
            resolved = PsqlDbContext.resolve_database_url(config, vault)

        self.assertEqual(
            resolved,
            "postgresql+asyncpg://config/config",
        )

    def test_migration_runner_reuses_runtime_database_resolution(self) -> None:
        config = _Config(
            vault_enabled=True,
            database_url="postgresql://config/config",
        )
        vault = VaultService(config)

        with patch.object(
            run_migrations,
            "ConfigReader",
            return_value=config,
        ), patch.object(
            run_migrations,
            "VaultService",
            return_value=vault,
        ), patch.object(
            run_migrations.PsqlDbContext,
            "resolve_database_url",
            return_value="postgresql+asyncpg://vault/vault",
        ) as resolver:
            self.assertEqual(
                run_migrations._database_url(),
                "postgresql+asyncpg://vault/vault",
            )

        resolver.assert_called_once_with(config, vault)

    def test_blank_database_url_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "non-empty"):
            PsqlDbContext.normalize_database_url("   ")


if __name__ == "__main__":
    unittest.main()
