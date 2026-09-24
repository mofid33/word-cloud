from __future__ import annotations

import math
import unittest

from src.core.services.semantic.providers.embedding_provider import EmbeddingProvider
from src.core.services.semantic.providers.provider_metadata import SemanticProviderMetadata
from src.core.services.semantic.providers.reranker_provider import RerankerProvider
from src.core.services.semantic.semantic_analysis_service import SemanticAnalysisService
from src.core.services.statistical.statistical_analysis_service import (
    StatisticalCandidateResult,
)


_METADATA = SemanticProviderMetadata(
    provider="test",
    provider_version="1",
    model_identifier="deterministic-test-double",
    model_revision=None,
    device="cpu",
    configuration_fingerprint="test",
)


class _Config:
    def __init__(self, top_n=2):
        self.top_n = top_n

    def require(self, key: str):
        if key == "semantic_analysis.rerank_top_n":
            return self.top_n
        raise KeyError(key)


class _Embedding(EmbeddingProvider):
    @property
    def metadata(self):
        return _METADATA

    async def embed_async(self, texts):
        mapping = {
            "هوش مصنوعی در آموزش": (1.0, 0.0),
            "هوش مصنوعی": (1.0, 0.0),
            "یادگیری ماشین": (0.8, 0.2),
            "آشپزی": (-1.0, 0.0),
        }
        return tuple(mapping[text] for text in texts)


class _Reranker(RerankerProvider):
    @property
    def metadata(self):
        return _METADATA

    async def rerank_async(self, query, candidates):
        values = {"هوش مصنوعی": 0.95, "یادگیری ماشین": 0.70}
        return tuple(values[candidate] for candidate in candidates)


def _candidate(text: str) -> StatisticalCandidateResult:
    return StatisticalCandidateResult(
        text=text,
        canonical_text=text,
        ngram_size=2,
        frequency=1,
        relative_frequency=1 / 3,
        normalized_frequency=1.0,
        document_frequency=1,
        document_coverage=1.0,
        section_coverage=None,
        chunk_coverage=None,
        phrase_quality=2 / 3,
        statistical_score=0.5,
        is_protected=False,
        contains_stopword=False,
        pos_tags=(None, None),
        occurrences=(),
    )


class SemanticAnalysisServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_top_n_reranking_and_fallback_are_deterministic(self):
        service = SemanticAnalysisService(_Embedding(), _Reranker(), _Config())
        candidates = tuple(
            _candidate(text)
            for text in ("آشپزی", "یادگیری ماشین", "هوش مصنوعی")
        )
        result = await service.analyze_async("هوش مصنوعی در آموزش", candidates)
        self.assertEqual(
            [item.canonical_text for item in result.candidates],
            ["هوش مصنوعی", "یادگیری ماشین", "آشپزی"],
        )
        self.assertEqual(result.candidates[0].reranker_score, 0.95)
        self.assertFalse(result.candidates[-1].reranked)
        self.assertEqual(result.candidates[-1].bi_encoder_score, 0.0)

    async def test_empty_candidates_is_valid(self):
        service = SemanticAnalysisService(_Embedding(), _Reranker(), _Config())
        result = await service.analyze_async("", ())
        self.assertEqual(result.candidates, ())

    async def test_one_candidate_and_top_n_above_candidate_count(self):
        service = SemanticAnalysisService(
            _Embedding(),
            _Reranker(),
            _Config(top_n=10),
        )
        result = await service.analyze_async(
            "هوش مصنوعی در آموزش",
            (_candidate("هوش مصنوعی"),),
        )
        self.assertEqual(len(result.candidates), 1)
        self.assertTrue(result.candidates[0].reranked)
        self.assertEqual(result.candidates[0].rank, 1)

    def test_non_positive_rerank_top_n_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "integer > 0"):
            SemanticAnalysisService(
                _Embedding(),
                _Reranker(),
                _Config(top_n=0),
            )

    async def test_duplicate_canonical_candidates_fail_fast(self):
        service = SemanticAnalysisService(_Embedding(), _Reranker(), _Config())
        candidate = _candidate("هوش مصنوعی")
        with self.assertRaisesRegex(ValueError, "unique canonical_text"):
            await service.analyze_async("هوش مصنوعی در آموزش", (candidate, candidate))

    async def test_nan_reranker_score_is_rejected(self):
        class InvalidReranker(_Reranker):
            async def rerank_async(self, query, candidates):
                return (math.nan,) * len(candidates)

        service = SemanticAnalysisService(_Embedding(), InvalidReranker(), _Config())
        with self.assertRaisesRegex(ValueError, "finite"):
            await service.analyze_async(
                "هوش مصنوعی در آموزش",
                (_candidate("هوش مصنوعی"), _candidate("یادگیری ماشین")),
            )

    async def test_non_finite_embedding_value_is_rejected(self):
        class InvalidEmbedding(_Embedding):
            async def embed_async(self, texts):
                return (
                    (1.0, 0.0),
                    (math.inf, 0.0),
                )

        service = SemanticAnalysisService(
            InvalidEmbedding(),
            _Reranker(),
            _Config(),
        )
        with self.assertRaisesRegex(ValueError, "NaN or Inf"):
            await service.analyze_async(
                "هوش مصنوعی در آموزش",
                (_candidate("هوش مصنوعی"),),
            )

    async def test_zero_norm_embedding_is_rejected(self):
        class ZeroEmbedding(_Embedding):
            async def embed_async(self, texts):
                return (
                    (1.0, 0.0),
                    (0.0, 0.0),
                )

        service = SemanticAnalysisService(
            ZeroEmbedding(),
            _Reranker(),
            _Config(),
        )
        with self.assertRaisesRegex(ValueError, "zero-norm"):
            await service.analyze_async(
                "هوش مصنوعی در آموزش",
                (_candidate("هوش مصنوعی"),),
            )

    async def test_invalid_embedding_output_length_is_rejected(self):
        class InvalidEmbedding(_Embedding):
            async def embed_async(self, texts):
                return ((1.0, 0.0),)

        service = SemanticAnalysisService(InvalidEmbedding(), _Reranker(), _Config())
        with self.assertRaisesRegex(ValueError, "invalid output length"):
            await service.analyze_async(
                "هوش مصنوعی در آموزش",
                (_candidate("هوش مصنوعی"),),
            )

    async def test_duplicate_scores_use_canonical_text_tie_breaking(self):
        class TieEmbedding(EmbeddingProvider):
            @property
            def metadata(self):
                return _METADATA

            async def embed_async(self, texts):
                return tuple((1.0, 0.0) for _ in texts)

        class TieReranker(RerankerProvider):
            @property
            def metadata(self):
                return _METADATA

            async def rerank_async(self, query, candidates):
                return tuple(0.5 for _ in candidates)

        service = SemanticAnalysisService(
            TieEmbedding(),
            TieReranker(),
            _Config(top_n=10),
        )
        result = await service.analyze_async(
            "زمینه",
            (_candidate("ب"), _candidate("الف")),
        )
        self.assertEqual(
            [item.canonical_text for item in result.candidates],
            ["الف", "ب"],
        )


if __name__ == "__main__":
    unittest.main()
