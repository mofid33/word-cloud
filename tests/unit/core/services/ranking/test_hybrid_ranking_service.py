from __future__ import annotations

import asyncio
import math
import unittest

from src.core.services.ranking.hybrid_ranking_service import (
    FusionWeights,
    HybridRankingService,
)
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
    provider="test",
    provider_version="1",
    model_identifier="test-embedding",
    model_revision="1",
    device="cpu",
    configuration_fingerprint="test",
)


class _Config:
    def __init__(self, overrides=None):
        self.values = {
            "hybrid_ranking.normalization_strategy": "min_max",
            "hybrid_ranking.baseline_weights.statistical": 0.5,
            "hybrid_ranking.baseline_weights.semantic": 0.5,
            "hybrid_ranking.lexical_deduplication_threshold": 0.92,
            "hybrid_ranking.mmr_lambda": 0.7,
            "hybrid_ranking.diversity_candidate_pool_size": 10,
            "hybrid_ranking.maximum_ranked_results": 5,
        }
        self.values.update(overrides or {})

    def require(self, key):
        if key not in self.values:
            raise KeyError(key)
        return self.values[key]


class _Embedding(EmbeddingProvider):
    @property
    def metadata(self):
        return _METADATA

    async def embed_async(self, texts):
        vectors = {
            "هوش مصنوعی": (1.0, 0.0, 0.0),
            "هوش مصنوعی پیشرفته": (0.99, 0.01, 0.0),
            "یادگیری ماشین": (0.8, 0.2, 0.0),
            "تحلیل داده": (0.0, 1.0, 0.0),
            "GPT-4": (0.0, 0.0, 1.0),
            "BERT-base": (0.1, 0.0, 0.9),
            "alpha": (1.0, 0.0, 0.0),
            "beta": (0.0, 1.0, 0.0),
            "gamma": (0.0, 0.0, 1.0),
        }
        return tuple(vectors.get(text, (0.5, 0.5, 0.5)) for text in texts)


def _stat(
    canonical: str,
    score: float,
    *,
    text: str | None = None,
    protected: bool = False,
) -> StatisticalCandidateResult:
    return StatisticalCandidateResult(
        text=text or canonical,
        canonical_text=canonical,
        ngram_size=max(1, min(3, len(canonical.split()))),
        frequency=1,
        relative_frequency=0.1,
        normalized_frequency=score if math.isfinite(score) else 0.0,
        document_frequency=1,
        document_coverage=1.0,
        section_coverage=None,
        chunk_coverage=None,
        phrase_quality=1.0,
        statistical_score=score,
        is_protected=protected,
        contains_stopword=False,
        pos_tags=(),
        occurrences=(),
    )


def _semantic(canonical: str, score: float, rank: int) -> SemanticCandidateResult:
    return SemanticCandidateResult(
        text=canonical,
        canonical_text=canonical,
        bi_encoder_similarity=0.0,
        bi_encoder_score=score if math.isfinite(score) else 0.0,
        reranker_score=score if math.isfinite(score) else None,
        semantic_score=score,
        reranked=True,
        rank=rank,
    )


def _result(candidates) -> SemanticAnalysisResult:
    return SemanticAnalysisResult(
        candidates=tuple(candidates),
        embedding_metadata=_METADATA,
        reranker_metadata=_METADATA,
        similarity_metric="cosine",
        semantic_score_strategy="test",
        rerank_top_n=25,
    )


class HybridRankingServiceTests(unittest.IsolatedAsyncioTestCase):
    def service(self, overrides=None):
        return HybridRankingService(_Embedding(), _Config(overrides))

    async def test_empty_candidates(self):
        ranked = await self.service().rank_async((), _result(()))
        self.assertEqual(ranked.candidates, ())
        self.assertEqual(ranked.deduplicated, ())

    async def test_one_candidate(self):
        ranked = await self.service().rank_async(
            (_stat("GPT-4", 0.4),),
            _result((_semantic("GPT-4", 0.8, 1),)),
        )
        self.assertEqual(len(ranked.candidates), 1)
        self.assertEqual(ranked.candidates[0].rank, 1)
        self.assertEqual(ranked.candidates[0].normalized_statistical_score, 1.0)
        self.assertEqual(ranked.candidates[0].normalized_semantic_score, 1.0)

    async def test_min_max_normalization_and_fusion(self):
        ranked = await self.service().rank_async(
            (_stat("alpha", 0.0), _stat("beta", 0.5), _stat("gamma", 1.0)),
            _result((
                _semantic("alpha", 1.0, 1),
                _semantic("beta", 0.5, 2),
                _semantic("gamma", 0.0, 3),
            )),
            maximum_results=3,
        )
        by_id = {item.canonical_text: item for item in ranked.candidates}
        self.assertAlmostEqual(by_id["alpha"].normalized_statistical_score, 0.0)
        self.assertAlmostEqual(by_id["alpha"].normalized_semantic_score, 1.0)
        self.assertAlmostEqual(by_id["alpha"].fused_score, 0.5)
        self.assertAlmostEqual(by_id["beta"].fused_score, 0.5)
        self.assertAlmostEqual(by_id["gamma"].fused_score, 0.5)

    async def test_constant_scores_are_deterministic(self):
        stats = (_stat("beta", 0.5), _stat("alpha", 0.5))
        semantic = _result((_semantic("beta", 0.5, 2), _semantic("alpha", 0.5, 1)))
        first = await self.service().rank_async(stats, semantic, maximum_results=2)
        second = await self.service().rank_async(tuple(reversed(stats)), semantic, maximum_results=2)
        self.assertEqual(
            [item.canonical_text for item in first.candidates],
            [item.canonical_text for item in second.candidates],
        )

    async def test_candidate_identity_mismatch_fails_fast(self):
        with self.assertRaisesRegex(ValueError, "identities do not match"):
            await self.service().rank_async(
                (_stat("alpha", 0.5),),
                _result((_semantic("beta", 0.5, 1),)),
            )

    async def test_duplicate_candidate_identity_fails_fast(self):
        duplicate = _stat("alpha", 0.5)
        with self.assertRaisesRegex(ValueError, "duplicate canonical_text"):
            await self.service().rank_async(
                (duplicate, duplicate),
                _result((_semantic("alpha", 0.5, 1),)),
            )

    async def test_nan_and_inf_scores_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "finite"):
            await self.service().rank_async(
                (_stat("alpha", math.nan),),
                _result((_semantic("alpha", 0.5, 1),)),
            )
        with self.assertRaisesRegex(ValueError, "finite"):
            await self.service().rank_async(
                (_stat("alpha", 0.5),),
                _result((_semantic("alpha", math.inf, 1),)),
            )

    async def test_exact_text_deduplication(self):
        ranked = await self.service().rank_async(
            (
                _stat("هوش مصنوعی", 0.9, text="AI"),
                _stat("یادگیری ماشین", 0.8, text="AI"),
            ),
            _result((
                _semantic("هوش مصنوعی", 0.9, 1),
                _semantic("یادگیری ماشین", 0.8, 2),
            )),
            maximum_results=2,
        )
        self.assertEqual(len(ranked.candidates), 1)
        self.assertEqual(ranked.deduplicated[0].reason, "exact_text")

    async def test_canonical_casefold_deduplication(self):
        ranked = await self.service().rank_async(
            (_stat("GPT-4", 0.9), _stat("gpt-4", 0.8)),
            _result((_semantic("GPT-4", 0.9, 1), _semantic("gpt-4", 0.8, 2))),
            maximum_results=2,
        )
        self.assertEqual(len(ranked.candidates), 1)
        self.assertEqual(ranked.deduplicated[0].reason, "canonical")

    async def test_lexical_near_duplicate_deduplication(self):
        ranked = await self.service({"hybrid_ranking.lexical_deduplication_threshold": 0.7}).rank_async(
            (
                _stat("هوش مصنوعی", 0.9),
                _stat("هوش مصنوعی پیشرفته", 0.8),
            ),
            _result((
                _semantic("هوش مصنوعی", 0.9, 1),
                _semantic("هوش مصنوعی پیشرفته", 0.8, 2),
            )),
            maximum_results=2,
        )
        self.assertEqual(len(ranked.candidates), 1)
        self.assertEqual(ranked.deduplicated[0].reason, "lexical_near_duplicate")

    async def test_protected_terms_bypass_near_duplicate_filter(self):
        ranked = await self.service({"hybrid_ranking.lexical_deduplication_threshold": 0.7}).rank_async(
            (
                _stat("هوش مصنوعی", 0.9, protected=True),
                _stat("هوش مصنوعی پیشرفته", 0.8),
            ),
            _result((
                _semantic("هوش مصنوعی", 0.9, 1),
                _semantic("هوش مصنوعی پیشرفته", 0.8, 2),
            )),
            maximum_results=2,
        )
        self.assertEqual(len(ranked.candidates), 2)

    async def test_mmr_promotes_diversity(self):
        ranked = await self.service({
            "hybrid_ranking.lexical_deduplication_threshold": 1.0,
            "hybrid_ranking.mmr_lambda": 0.4,
        }).rank_async(
            (
                _stat("هوش مصنوعی", 1.0),
                _stat("هوش مصنوعی پیشرفته", 0.95),
                _stat("تحلیل داده", 0.9),
            ),
            _result((
                _semantic("هوش مصنوعی", 1.0, 1),
                _semantic("هوش مصنوعی پیشرفته", 0.95, 2),
                _semantic("تحلیل داده", 0.9, 3),
            )),
            maximum_results=2,
        )
        self.assertEqual(ranked.candidates[0].canonical_text, "هوش مصنوعی")
        self.assertEqual(ranked.candidates[1].canonical_text, "تحلیل داده")

    async def test_override_weights_are_supported_for_phase_10(self):
        ranked = await self.service().rank_async(
            (_stat("alpha", 1.0), _stat("beta", 0.0)),
            _result((_semantic("alpha", 0.0, 2), _semantic("beta", 1.0, 1))),
            weights=FusionWeights(statistical=1.0, semantic=0.0),
            maximum_results=1,
        )
        self.assertEqual(ranked.candidates[0].canonical_text, "alpha")

    async def test_repeated_and_concurrent_execution_are_deterministic(self):
        stats = (_stat("GPT-4", 0.9), _stat("BERT-base", 0.8))
        semantic = _result((_semantic("GPT-4", 0.8, 1), _semantic("BERT-base", 0.7, 2)))
        service = self.service()
        first, second = await asyncio.gather(
            service.rank_async(stats, semantic, maximum_results=2),
            service.rank_async(tuple(reversed(stats)), semantic, maximum_results=2),
        )
        self.assertEqual(first.candidates, second.candidates)

    def test_invalid_configuration_is_rejected(self):
        invalid = [
            {"hybrid_ranking.baseline_weights.statistical": True},
            {"hybrid_ranking.baseline_weights.statistical": math.nan},
            {"hybrid_ranking.baseline_weights.statistical": 0.8},
            {"hybrid_ranking.lexical_deduplication_threshold": 1.1},
            {"hybrid_ranking.mmr_lambda": -0.1},
            {"hybrid_ranking.diversity_candidate_pool_size": 0},
            {
                "hybrid_ranking.diversity_candidate_pool_size": 2,
                "hybrid_ranking.maximum_ranked_results": 3,
            },
            {"hybrid_ranking.normalization_strategy": "zscore"},
        ]
        for overrides in invalid:
            with self.subTest(overrides=overrides):
                with self.assertRaises(ValueError):
                    self.service(overrides)

    async def test_invalid_override_weights_and_top_n_are_rejected(self):
        with self.assertRaises(ValueError):
            await self.service().rank_async(
                (_stat("alpha", 0.5),),
                _result((_semantic("alpha", 0.5, 1),)),
                weights=FusionWeights(0.8, 0.8),
            )
        with self.assertRaises(ValueError):
            await self.service().rank_async(
                (_stat("alpha", 0.5),),
                _result((_semantic("alpha", 0.5, 1),)),
                maximum_results=True,
            )
        with self.assertRaisesRegex(ValueError, "diversity_candidate_pool_size"):
            await self.service().rank_async(
                (_stat("alpha", 0.5),),
                _result((_semantic("alpha", 0.5, 1),)),
                maximum_results=11,
            )


if __name__ == "__main__":
    unittest.main()
