import subprocess
import sys
import unittest


class StartupSmokeTests(unittest.TestCase):
    def test_application_foundation_boots(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "from src.host.app import app; "
                    "assert app.title == "
                    "'Persian Semantic Text Analytics Service'"
                ),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            result.returncode,
            0,
            msg=result.stderr,
        )


if __name__ == "__main__":
    unittest.main()
