from __future__ import annotations

import importlib
import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class ProductionMigrationInvocationTests(unittest.TestCase):
    def test_migration_runner_is_importable_as_module(self) -> None:
        module = importlib.import_module(
            "src.infrastructure.scripts.run_migrations"
        )
        self.assertTrue(callable(module.main))

        stdout = io.StringIO()
        with patch.object(sys, "argv", ["run_migrations", "--help"]):
            with redirect_stdout(stdout):
                with self.assertRaises(SystemExit) as context:
                    module.main()

        self.assertEqual(context.exception.code, 0)
        self.assertIn("Manage database migrations", stdout.getvalue())

    def test_production_compose_uses_module_invocation(self) -> None:
        compose_path = PROJECT_ROOT / "compose.production.yaml"
        data = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
        self.assertEqual(
            data["services"]["migrate"]["command"],
            [
                "python",
                "-m",
                "src.infrastructure.scripts.run_migrations",
                "--upgrade",
            ],
        )


if __name__ == "__main__":
    unittest.main()
