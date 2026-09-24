from __future__ import annotations

import os
import unittest

from src.core.services.candidate.candidate_extraction_service import (
    CandidateDocument,
    CandidateExtractionService,
)
from src.core.services.persian_text.persian_text_processor import PersianTextProcessor
from src.core.services.ranking.hybrid_ranking_service import HybridRankingService
from src.core.services.semantic.providers.embedding_provider import EmbeddingProvider
from src.core.services.semantic.semantic_analysis_service import SemanticAnalysisService
from src.core.services.statistical.statistical_analysis_service import (
    StatisticalAnalysisService,
)
from src.infrastructure.di.bootstrap import bootstrap_di
from src.infrastructure.di.inject import reset_di_state, resolve


class HybridRankingDiscoveryIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_di_state()
        bootstrap_di()

    def test_hybrid_ranking_service_resolves_with_real_dependencies(self) -> None:
        ranking = resolve(HybridRankingService)
        embedding = resolve(EmbeddingProvider)

        self.assertIs(ranking._embedding_provider, embedding)
        self.assertEqual(ranking.config.normalization_strategy, "min_max")
        self.assertEqual(ranking.config.baseline_weights.statistical, 0.5)
        self.assertEqual(ranking.config.baseline_weights.semantic, 0.5)


@unittest.skipUnless(
    os.getenv("RUN_PHASE8_MODEL_INTEGRATION") == "1",
    "set RUN_PHASE8_MODEL_INTEGRATION=1 with configured models available",
)
class HybridRankingPipelineIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        reset_di_state()
        bootstrap_di()

    async def test_phase_6_to_phase_9_real_di_pipeline(self) -> None:
        processor = resolve(PersianTextProcessor)
        extractor = resolve(CandidateExtractionService)
        statistical = resolve(StatisticalAnalysisService)
        semantic = resolve(SemanticAnalysisService)
        ranking = resolve(HybridRankingService)

        processing = processor.process(
            "هوش مصنوعی و یادگیری ماشین در تحلیل داده کاربرد دارند و GPT-4 نمونه فنی است",
            domain="COURSE",
        )
        document = CandidateDocument(
            "course-1",
            processing,
            section_id="s1",
            chunk_id="c1",
        )
        occurrences = extractor.extract_documents((document,))
        statistics = statistical.analyze(
            occurrences,
            document_ids=("course-1",),
            section_keys=(("course-1", "s1"),),
            chunk_keys=(("course-1", "c1"),),
        )
        semantic_result = await semantic.analyze_async(
            processing.embedding_text,
            statistics,
        )
        hybrid_result = await ranking.rank_async(
            statistics,
            semantic_result,
            maximum_results=min(10, max(1, len(statistics))),
        )

        self.assertTrue(hybrid_result.candidates)
        self.assertLessEqual(len(hybrid_result.candidates), 10)
        self.assertEqual(
            [item.rank for item in hybrid_result.candidates],
            list(range(1, len(hybrid_result.candidates) + 1)),
        )
        self.assertTrue(
            all(0.0 <= item.fused_score <= 1.0 for item in hybrid_result.candidates)
        )
        self.assertEqual(
            hybrid_result.embedding_metadata.provider,
            semantic_result.embedding_metadata.provider,
        )
        self.assertEqual(hybrid_result.scoring_version, "hybrid-ranking-v2")


if __name__ == "__main__":
    unittest.main()
