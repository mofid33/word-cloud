from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class ProductionMigrationInvocationTests(unittest.TestCase):
    def test_migration_runner_is_importable_as_module(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "src.infrastructure.scripts.run_migrations",
                "--help",
            ],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("Manage database migrations", result.stdout)

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
