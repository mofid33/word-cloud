from __future__ import annotations

import asyncio
import os
import unittest
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
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


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "TEST_DATABASE_URL is required for migration integration tests",
)
class MigrationIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_upgrade_creates_and_downgrade_removes_phase_four_schema(self) -> None:
        url = _test_database_url()
        assert url is not None

        config = Config()
        config.set_main_option("script_location", str(ALEMBIC_DIR))
        config.set_main_option("sqlalchemy.url", url)

        await asyncio.to_thread(command.downgrade, config, "base")
        await asyncio.to_thread(command.upgrade, config, "head")

        engine = create_async_engine(url)
        try:
            async with engine.connect() as connection:
                table_names = set(
                    await connection.run_sync(
                        lambda sync_connection: inspect(sync_connection).get_table_names()
                    )
                )
            self.assertTrue(
                {
                    "word_cloud_analysis",
                    "analysis_document",
                    "analysis_keyword",
                    "analysis_topic",
                    "analysis_topic_keyword",
                    "alembic_version",
                }.issubset(table_names)
            )
        finally:
            await engine.dispose()

        await asyncio.to_thread(command.downgrade, config, "base")

        engine = create_async_engine(url)
        try:
            async with engine.connect() as connection:
                table_names = set(
                    await connection.run_sync(
                        lambda sync_connection: inspect(sync_connection).get_table_names()
                    )
                )
            self.assertNotIn("word_cloud_analysis", table_names)
        finally:
            await engine.dispose()


if __name__ == "__main__":
    unittest.main()
