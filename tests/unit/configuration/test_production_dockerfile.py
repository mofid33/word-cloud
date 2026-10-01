from __future__ import annotations

import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class ProductionDockerfileTests(unittest.TestCase):
    def test_default_image_uses_cpu_pytorch_index_before_requirements(self) -> None:
        dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")
        cpu_index = "https://download.pytorch.org/whl/cpu"
        self.assertIn(cpu_index, dockerfile)
        torch_install = dockerfile.index('"${TORCH_SPEC}"')
        requirements_install = dockerfile.index("--requirement /app/requirements.txt")
        self.assertLess(torch_install, requirements_install)

    def test_build_records_resolved_dependency_inventory(self) -> None:
        dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn(
            "/opt/word-cloud/resolved-dependencies.txt",
            dockerfile,
        )
        self.assertIn("pip freeze --all", dockerfile)

    def test_large_dependency_downloads_have_retry_and_resume_policy(self) -> None:
        dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("--retries 10", dockerfile)
        self.assertIn("--resume-retries 20", dockerfile)


if __name__ == "__main__":
    unittest.main()
