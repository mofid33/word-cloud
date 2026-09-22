from __future__ import annotations

import argparse
import os
from pathlib import Path

from alembic import command
from alembic.config import Config

from src.infrastructure.utils.config_reader import ConfigReader


PROJECT_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_DIR = PROJECT_ROOT / "src" / "infrastructure" / "alembic"


def _database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    configured = str(ConfigReader().require("database.url"))
    if configured.startswith("postgresql://"):
        return configured.replace("postgresql://", "postgresql+asyncpg://", 1)
    return configured


def _build_config() -> Config:
    config = Config()
    config.set_main_option("script_location", str(ALEMBIC_DIR))
    config.set_main_option("sqlalchemy.url", _database_url())
    return config


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage database migrations")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--upgrade", action="store_true")
    action.add_argument("--downgrade", action="store_true")
    action.add_argument("--autogenerate", action="store_true")
    action.add_argument("--sync", action="store_true")
    parser.add_argument("-m", "--message")
    parser.add_argument(
        "--revision",
        default="-1",
        help="Downgrade target; defaults to one revision back",
    )
    args = parser.parse_args()
    config = _build_config()

    if args.upgrade:
        command.upgrade(config, "head")
        return

    if args.downgrade:
        command.downgrade(config, args.revision)
        return

    if not args.message:
        parser.error("-m/--message is required with --autogenerate or --sync")

    command.revision(config, message=args.message, autogenerate=True)
    if args.sync:
        command.upgrade(config, "head")


if __name__ == "__main__":
    main()
