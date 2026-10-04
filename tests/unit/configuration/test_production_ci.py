from __future__ import annotations

import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class ProductionCiContractTests(unittest.TestCase):
    def test_worker_health_gate_waits_for_healthy_state(self) -> None:
        workflow = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("docker inspect --format", workflow)
        self.assertIn('"healthy"', workflow)
        self.assertIn('"unhealthy"', workflow)
        self.assertIn("exit 1", workflow)

    def test_graceful_stop_gate_requires_clean_exit(self) -> None:
        workflow = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("Graceful stop smoke", workflow)
        self.assertIn(".State.ExitCode", workflow)
        self.assertIn(".State.OOMKilled", workflow)
        self.assertIn('= "0"', workflow)
        self.assertIn('= "false"', workflow)

    def test_compose_grace_period_exceeds_internal_worker_timeout(self) -> None:
        compose = (PROJECT_ROOT / "compose.production.yaml").read_text(
            encoding="utf-8"
        )
        production = (
            PROJECT_ROOT / "src" / "host" / "res" / "appsettings.yaml"
        ).read_text(encoding="utf-8")
        self.assertGreaterEqual(compose.count("stop_grace_period: 60s"), 2)
        self.assertIn("graceful_shutdown_seconds: 30", production)


if __name__ == "__main__":
    unittest.main()
