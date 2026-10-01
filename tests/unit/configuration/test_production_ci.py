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


if __name__ == "__main__":
    unittest.main()
