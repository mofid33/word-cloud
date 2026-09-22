from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from src.infrastructure.context.sql_db.psql_dbcontext import Base, PsqlDbContext
from src.infrastructure.context.vault.vault_service import VaultService
from src.infrastructure.models.analysis_document import AnalysisDocument
from src.infrastructure.models.analysis_keyword import AnalysisKeyword
from src.infrastructure.models.analysis_topic import AnalysisTopic
from src.infrastructure.models.analysis_topic_keyword import AnalysisTopicKeyword
from src.infrastructure.models.word_cloud_analysis import WordCloudAnalysis
from src.infrastructure.utils.config_reader import ConfigReader


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

_MODEL_IMPORTS = (
    WordCloudAnalysis,
    AnalysisDocument,
    AnalysisKeyword,
    AnalysisTopic,
    AnalysisTopicKeyword,
)


def _database_url() -> str:
    configured = config.get_main_option("sqlalchemy.url")
    if configured:
        return configured

    config_reader = ConfigReader()
    vault_service = VaultService(config_reader)
    return PsqlDbContext.resolve_database_url(
        config_reader,
        vault_service,
    )


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = _database_url()
    connectable = async_engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
