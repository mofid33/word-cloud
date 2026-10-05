from __future__ import annotations

import asyncio
import os
import unittest
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Text, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine


PROJECT_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_DIR = PROJECT_ROOT / "src" / "infrastructure" / "alembic"


def _test_database_url() -> str | None:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        return None
    database_name = make_url(url).database or ""
    if "test" not in database_name.lower():
        raise RuntimeError(
            "TEST_DATABASE_URL must point to a database whose name contains 'test'"
        )
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


async def _reset_public_schema(url: str) -> None:
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            await connection.execute(text("CREATE SCHEMA public"))
    finally:
        await engine.dispose()


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "TEST_DATABASE_URL is required for migration integration tests",
)
class MigrationIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_upgrade_creates_and_downgrade_removes_current_schema(self) -> None:
        url = _test_database_url()
        assert url is not None

        config = Config()
        config.set_main_option("script_location", str(ALEMBIC_DIR))
        config.set_main_option("sqlalchemy.url", url)

        await _reset_public_schema(url)
        try:
            await asyncio.to_thread(command.upgrade, config, "head")

            engine = create_async_engine(url)
            try:
                async with engine.connect() as connection:
                    table_names = set(
                        await connection.run_sync(
                            lambda sync_connection: inspect(
                                sync_connection
                            ).get_table_names()
                        )
                    )
                    queue_indexes = {
                        item["name"]
                        for item in await connection.run_sync(
                            lambda sync_connection: inspect(
                                sync_connection
                            ).get_indexes("analysis_queue_job")
                        )
                    }
                    analysis_columns = {
                        item["name"]: item
                        for item in await connection.run_sync(
                            lambda sync_connection: inspect(
                                sync_connection
                            ).get_columns("word_cloud_analysis")
                        )
                    }
                    revision = await connection.scalar(
                        text("SELECT version_num FROM alembic_version")
                    )

                self.assertTrue(
                    {
                        "word_cloud_analysis",
                        "analysis_document",
                        "analysis_keyword",
                        "analysis_topic",
                        "analysis_topic_keyword",
                        "analysis_queue_job",
                        "alembic_version",
                    }.issubset(table_names)
                )
                self.assertTrue(
                    {
                        "ix_analysis_queue_job_available",
                        "ix_analysis_queue_job_lease_expiry",
                    }.issubset(queue_indexes)
                )
                self.assertIsInstance(
                    analysis_columns["model_version"]["type"],
                    Text,
                )
                self.assertEqual(revision, "20261005_0003")
            finally:
                await engine.dispose()

            await asyncio.to_thread(command.downgrade, config, "base")

            engine = create_async_engine(url)
            try:
                async with engine.connect() as connection:
                    table_names = set(
                        await connection.run_sync(
                            lambda sync_connection: inspect(
                                sync_connection
                            ).get_table_names()
                        )
                    )
                self.assertNotIn("word_cloud_analysis", table_names)
                self.assertNotIn("analysis_queue_job", table_names)
            finally:
                await engine.dispose()
        finally:
            await _reset_public_schema(url)


if __name__ == "__main__":
    unittest.main()
