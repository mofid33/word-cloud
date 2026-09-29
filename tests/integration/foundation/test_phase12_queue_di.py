import unittest

from src.core.services.analysis.providers.analysis_queue_provider import (
    AnalysisQueueProvider,
)
from src.infrastructure.di.bootstrap import bootstrap_di
from src.infrastructure.di.inject import reset_di_state, resolve
from src.infrastructure.providers.analysis_queue.postgres_analysis_queue_provider import (
    PostgresAnalysisQueueProvider,
)


class Phase12DiDiscoveryTests(unittest.TestCase):
    def tearDown(self) -> None:
        reset_di_state()

    def test_queue_provider_is_discovered_for_interface(self) -> None:
        reset_di_state()
        imported = bootstrap_di()

        self.assertIn(
            "src.infrastructure.providers.analysis_queue.postgres_analysis_queue_provider",
            imported,
        )
        provider = resolve(AnalysisQueueProvider)
        self.assertIsInstance(provider, PostgresAnalysisQueueProvider)


if __name__ == "__main__":
    unittest.main()
