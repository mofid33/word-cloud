from __future__ import annotations

import unittest
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class LocalComposeTests(unittest.TestCase):
    def test_compose_provides_postgres_dependency_with_healthcheck(self) -> None:
        compose = yaml.safe_load(
            (PROJECT_ROOT / "compose.yaml").read_text(encoding="utf-8")
        )
        postgres = compose["services"]["postgres"]

        self.assertEqual(postgres["image"], "postgres:16-alpine")
        self.assertIn("healthcheck", postgres)
        self.assertIn("5432", str(postgres["ports"]))
        self.assertTrue(
            any(
                "docker-entrypoint-initdb.d" in volume
                for volume in postgres["volumes"]
            )
        )

    def test_test_database_initialization_is_present(self) -> None:
        init_sql = (
            PROJECT_ROOT
            / "docker"
            / "postgres"
            / "init"
            / "01-create-test-db.sql"
        ).read_text(encoding="utf-8")

        self.assertIn("word_cloud_test", init_sql)


if __name__ == "__main__":
    unittest.main()
