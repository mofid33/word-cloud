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


    def test_resource_limit_gate_requires_cpu_memory_and_pid_limits(self) -> None:
        workflow = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
        compose = (PROJECT_ROOT / "compose.production.yaml").read_text(
            encoding="utf-8"
        )

        self.assertIn("Verify container resource limits", workflow)
        self.assertIn(".HostConfig.Memory", workflow)
        self.assertIn(".HostConfig.NanoCpus", workflow)
        self.assertIn(".HostConfig.PidsLimit", workflow)
        self.assertIn('cpus: "${API_CPU_LIMIT:-4.0}"', compose)
        self.assertIn('mem_limit: "${API_MEMORY_LIMIT:-6g}"', compose)
        self.assertIn("pids_limit: ${API_PIDS_LIMIT:-512}", compose)
        self.assertIn('cpus: "${WORKER_CPU_LIMIT:-4.0}"', compose)
        self.assertIn('mem_limit: "${WORKER_MEMORY_LIMIT:-6g}"', compose)
        self.assertIn("pids_limit: ${WORKER_PIDS_LIMIT:-512}", compose)


if __name__ == "__main__":
    unittest.main()
