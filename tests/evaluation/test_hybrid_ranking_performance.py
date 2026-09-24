from __future__ import annotations

import json
import os
import time
import tracemalloc
import unittest

from src.core.services.ranking.hybrid_ranking_service import HybridRankingService
from src.core.services.semantic.providers.embedding_provider import EmbeddingProvider
from src.core.services.semantic.providers.provider_metadata import SemanticProviderMetadata
from src.core.services.semantic.semantic_analysis_service import (
    SemanticAnalysisResult,
    SemanticCandidateResult,
)
from src.core.services.statistical.statistical_analysis_service import (
    StatisticalCandidateResult,
)


_METADATA = SemanticProviderMetadata(
    provider="phase9-performance",
    provider_version="1",
    model_identifier="deterministic-performance-vectorizer",
    model_revision="1",
    device="cpu",
    configuration_fingerprint="phase9-performance",
)


class _Config:
    def require(self, key):
        values = {
            "hybrid_ranking.normalization_strategy": "min_max",
            "hybrid_ranking.baseline_weights.statistical": 0.5,
            "hybrid_ranking.baseline_weights.semantic": 0.5,
            "hybrid_ranking.lexical_deduplication_threshold": 0.99,
            "hybrid_ranking.mmr_lambda": 0.7,
            "hybrid_ranking.diversity_candidate_pool_size": 50,
            "hybrid_ranking.maximum_ranked_results": 25,
        }
        return values[key]


class _Embedding(EmbeddingProvider):
    @property
    def metadata(self):
        return _METADATA

    async def embed_async(self, texts):
        vectors = []
        for text in texts:
            seed = sum(ord(char) for char in text)
            vectors.append(
                (
                    float((seed % 97) + 1),
                    float((seed % 89) + 1),
                    float((seed % 83) + 1),
                    float((seed % 79) + 1),
                )
            )
        return tuple(vectors)


def _stat(index: int, count: int) -> StatisticalCandidateResult:
    score = (count - index) / count
    canonical = f"candidate-{index:05d}"
    return StatisticalCandidateResult(
        text=canonical,
        canonical_text=canonical,
        ngram_size=1,
        frequency=1,
        relative_frequency=1 / count,
        normalized_frequency=score,
        document_frequency=1,
        document_coverage=1.0,
        section_coverage=None,
        chunk_coverage=None,
        phrase_quality=1 / 3,
        statistical_score=score,
        is_protected=False,
        contains_stopword=False,
        pos_tags=(),
        occurrences=(),
    )


def _semantic(index: int, count: int) -> SemanticCandidateResult:
    score = ((index * 37) % count) / max(1, count - 1)
    canonical = f"candidate-{index:05d}"
    return SemanticCandidateResult(
        text=canonical,
        canonical_text=canonical,
        bi_encoder_similarity=0.0,
        bi_encoder_score=score,
        reranker_score=score,
        semantic_score=score,
        reranked=True,
        rank=index + 1,
    )


class HybridRankingPerformanceTests(unittest.IsolatedAsyncioTestCase):
    async def test_candidate_scaling_and_bounded_mmr_pool(self):
        service = HybridRankingService(_Embedding(), _Config())
        evidence = {}

        for count in (100, 500, 1000):
            statistics = tuple(_stat(index, count) for index in range(count))
            semantic_result = SemanticAnalysisResult(
                candidates=tuple(_semantic(index, count) for index in range(count)),
                embedding_metadata=_METADATA,
                reranker_metadata=_METADATA,
                similarity_metric="cosine",
                semantic_score_strategy="performance_fixture",
                rerank_top_n=count,
            )

            tracemalloc.start()
            started = time.perf_counter()
            result = await service.rank_async(statistics, semantic_result)
            elapsed = time.perf_counter() - started
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()

            self.assertEqual(len(result.candidates), 25)
            self.assertEqual(result.diversity_candidate_pool_size, 50)
            evidence[str(count)] = {
                "elapsed_seconds": elapsed,
                "peak_tracemalloc_bytes": peak,
                "ranked_results": len(result.candidates),
                "configured_mmr_pool": result.diversity_candidate_pool_size,
            }

        optional_limit = os.getenv("PHASE9_PERF_MAX_SECONDS_1000")
        if optional_limit:
            limit = float(optional_limit)
            if limit <= 0:
                self.fail("PHASE9_PERF_MAX_SECONDS_1000 must be positive")
            self.assertLess(evidence["1000"]["elapsed_seconds"], limit)

        print("PHASE9_PERFORMANCE=" + json.dumps(evidence, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
